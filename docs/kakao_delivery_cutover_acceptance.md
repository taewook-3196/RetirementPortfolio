# Kakao delivery cutover acceptance gates

Status: **BLOCKED — no production migration, no cutover, no automatic resend**.

## Source-level findings

- `scripts/run_multi_user_morning_reports.py` is the scheduled entrypoint.
- `services/daily_report_service.py` calls `KakaoService.send_morning_report` before writing `morning_reports.kakao_sent_at`.
- The legacy `force_resend` input can intentionally resend and must not bypass staged duplicate protection.
- `services/kakao_delivery_staged.py` is not wired into production.

## Mandatory gates

1. **Single sender:** scheduled, manual, CLI and `send_cached_kakao` paths must share one durable claim; never run old and new senders concurrently.
2. **Database:** validate migration, RLS, grants and rollback on disposable PostgreSQL matching production before any production DDL.
3. **Concurrency:** simultaneous same-user/day invocations cause at most one transport call.
4. **Uncertain delivery:** timeouts, connection resets and DB commit uncertainty require manual reconciliation, never automatic resend.
5. **Legacy marker:** existing `kakao_sent_at` blocks new sending, including manual force paths.
6. **Atomic completion:** update the new attempt and legacy marker in the same committed transaction.
7. **Manual semantics:** report regeneration must be distinct from message retransmission; previously sent or uncertain messages need explicit reviewed recovery.
8. **Isolation:** verify per-user permissions and scrub tokens, IDs, report URLs and portfolio values from public logs.
9. **Rollback:** stop all senders, reconcile in-flight attempts, then switch a single authoritative sender; no mixed-version overlap.
10. **Operational acceptance:** read-only audit against actual delivery markers, controlled staging E2E, and explicit operator signoff outside morning delivery hours.

Do not set `KAKAO_DELIVERY_STATE_ENABLED=true` or `KAKAO_DELIVERY_CUTOVER_APPROVED=true` until these gates pass. Successful unit and disposable-Postgres tests do not establish live delivery correctness.

## Reviewed recovery protocol (not implemented or authorized)

A `failed_before_send` record is **not** a retry permit. The database
claim function refuses all historical attempts for the same user and date,
including pre-send failures. The partial unique index alone is insufficient.

1. Freeze the scheduled and manual send entrypoints for the affected user/date;
   do not toggle cutover flags or use the legacy force-resend path.
2. Identify the attempt by user, report date and attempt ID using a privileged,
   read-only inspection. Confirm the legacy `kakao_sent_at` marker is null.
3. Establish affirmative evidence that the Kakao network request never began.
   A timeout, missing log, expired lease, or generic API error is **not** proof.
   If evidence is absent, retain the blocked record and reconcile externally.
4. Record operator identity, evidence reference, approval time, affected attempt,
   and the intended recovery action in an access-controlled audit trail.
5. A future recovery implementation must atomically authorize one new claim
   under a per-user/date lock and recheck legacy and attempt markers. Never
   delete the prior attempt or simply flip its status to bypass the guard.
6. Verify one transport invocation, both success markers, and no other sender
   during a controlled disposable-DB/staging test before enabling any recovery.

**Current implementation deliberately provides no recovery write endpoint.**
Manual recovery remains blocked until audited approval, DB locking, access
control, and tests are implemented and reviewed.


## Evidence standard for any future positive recovery finding

A database status of `failed_before_send` describes the application's
classification, **not** independently verified proof that no HTTP request
left the process. A process crash can occur after network transmission and
before a durable success marker is written. In that case, retrying could
deliver a duplicate Kakao message.

- An operator's `request_never_started=True` assertion, free-text reason,
  ticket number, absence of logs, expired lease, timeout, or a local
  `failed_before_send` status is insufficient on its own.
- A positive finding would require trustworthy, correlated evidence from
  the actual transport boundary, tied to the attempt ID, user/date and
  exact request lifecycle. The evidence must distinguish a failure before
  dispatch from an ambiguous post-dispatch outcome, survive process crashes,
  and be independently reviewable. Do not assume ordinary application logs
  or provider receipts offer that guarantee.
- If the transport cannot establish this boundary durably, keep the
  attempt blocked and reconcile with the provider or recipient rather than
  automatically retrying.
- Current `append_recovery_audit` intentionally accepts only `denied`
  records. A caller-supplied `RecoveryAuditRecord` or a pure
  `assess_recovery_review` result is not a trusted evidence attestation.
  No positive decision, new claim, or send is authorized.
- Before changing that rule, require a separate security review, a
  server-generated evidence attestation, transactional revalidation,
  cross-user authorization tests, crash-window tests, and explicit operator
  approval. Keep the production cutover flags disabled until all acceptance
  gates are met.


## Sender entrypoint inventory (source inspection, 2026-10-14)

| Entrypoint | Current transport path | Cutover risk |
| --- | --- | --- |
| `scripts/run_multi_user_morning_reports.py` | Calls `DailyReportService.generate_and_send` | Scheduled job checks the legacy sent marker before sending, but a read-before-send check alone is not an atomic claim. |
| `DailyReportService.generate_and_send` | Calls `kakao_service.send_morning_report` directly, then writes `kakao_sent_at` | Concurrent invocations or a crash after provider acceptance and before marker commit can duplicate delivery. `force_kakao` bypasses the enabled preference, not a durable claim. |
| `DailyReportService.send_cached_kakao` | Calls `kakao_service.send_morning_report` directly | Does not claim an attempt or write the legacy sent marker; must be included in cutover or explicitly disabled. |
| `run_daily_report_cli` | Calls `generate_and_send`, or `send_cached_kakao` in cached mode | Both CLI branches must be covered by the same cutover gate. |
| `.github/workflows/morning_report.yml` | Three weekday cron entries plus manual `workflow_dispatch` with `force_resend` | Multiple scheduled/manual invocations may overlap; review KST conversion and all manual paths before enabling. |

**Current outcome:** these are known unsafe-to-mix legacy entrypoints,
not evidence of duplicate sends having occurred. The staged state module
is not wired to production. Do not enable either cutover flag yet.

### Required implementation before rollout

1. Inventory any additional web/admin/CLI callers of the service and ensure
   every sender is covered; prohibit mixed legacy and staged senders.
2. Create one trusted transport gateway that atomically claims by user/date
   **before** any HTTP dispatch, including cached/manual/forced sends.
3. Preserve existing report-generation behavior while separating regeneration
   from retransmission; never treat a force flag as permission to bypass claims.
4. In a disposable database, test simultaneous scheduled/manual/cached calls,
   a crash after dispatch, a DB completion failure, and a legacy marker conflict.
5. Freeze old workers and verify all old schedules and endpoints are disabled
   before any controlled cutover; do not attempt a rolling mixed-version rollout.
6. Keep the staged PR in draft until the full entrypoint inventory, acceptance
   tests, operational review and explicit production approval are complete.
