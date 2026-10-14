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


## Additional legacy scheduler risks verified in source

- `run_all_users(force=True)` bypasses the existing report's sent-marker
  skip branch and invokes `generate_and_send(..., force_kakao=send_kakao)`.
  The manual workflow input is named `force_resend` and explicitly requests
  Kakao retransmission. **Do not use this workflow input as a recovery
  mechanism** while the staged claim gateway is not wired.
- The GitHub Actions `concurrency: group: morning-report` serializes runs
  of that workflow group only. It cannot coordinate with web, CLI, other
  workflows, or workers, and is not a substitute for a DB claim.
- The three UTC cron schedules map to KST Tue–Sat morning (05:35, 07:10,
  09:00 respectively). Each run must independently respect the user's due
  time and durable delivery status.
- Current `run_all_users` can regenerate an existing unsent report and
  retry Kakao based only on a null legacy marker; null alone does not
  distinguish never-sent from an unrecorded successful send.
- During cutover, the `force_resend` UI should be renamed or disabled,
  and report regeneration must not imply Kakao retransmission. This
  requires a separate product/operations decision, not an automatic
  production behavior change in this draft PR.


## Pre-cutover acceptance matrix (2026-10-14)

| Gate | Current evidence | Status |
| --- | --- | --- |
| Fail-closed feature flags | Unit tests reject missing, partial, malformed flags before DB adapter initialization | TESTED (staged) |
| Single durable claim | PostgreSQL concurrent four-worker mock transport test | TESTED (staged) |
| Ambiguous provider outcome | PostgreSQL concurrent timeout, negative response and missing legacy-row completion tests | TESTED (staged) |
| Legacy sent marker | PostgreSQL adapter and SQL-function rejection tests | TESTED (staged) |
| Atomic success markers | PostgreSQL `finish_kakao_delivery_with_legacy` tests | TESTED (staged) |
| Per-user isolation / RLS | Disposable PostgreSQL permission and cross-user tests | TESTED (staged) |
| Regeneration separate from retransmission | Pure staged intent policy and boolean matrix tests | TESTED (policy only) |
| Full live entrypoint inventory and unified gateway | Production `DailyReportService` and CLI still use legacy transport | BLOCKED |
| Production-compatible migration rehearsal | Disposable PostgreSQL CI exists; production schema compatibility and deployment/rollback rehearsal unverified | BLOCKED |
| Safe manual force-resend semantics | Workflow currently exposes `force_resend`; no staged integration | BLOCKED |
| Trusted positive recovery evidence | Writer deliberately denies positive recovery; no trusted dispatch attestation | BLOCKED |
| Controlled staging E2E, rollback and operator approval | Not performed; no live send authorized | BLOCKED |

**Decision:** remain draft and keep both cutover flags disabled. A green CI
run only validates staged contracts against test fixtures, not the safety
of the still-active legacy senders.

### Next engineering sequence (no production effects)

1. Identify every direct call to `send_morning_report` and all web/admin,
   scheduled, manual, CLI and cached entrypoints. Add source-level guard
   tests to prevent accidentally omitting a sender during cutover.
2. Implement a trusted backend-only shared delivery adapter behind the
   two exact opt-in flags; replace legacy transport only as one complete,
   separately reviewed cutover change, never a partially migrated path.
3. Make manual regeneration a report-only operation by default. Require a
   separate, reviewed action for Kakao retransmission; a `force` boolean
   must never authorize delivery.
4. Rehearse schema migration and rollback on a disposable DB mirroring
   the production schema; verify cross-version lockout and crash windows.
5. Review runbooks and security, then request explicit approval before
   any production migration, rollout flag or real Kakao send.
