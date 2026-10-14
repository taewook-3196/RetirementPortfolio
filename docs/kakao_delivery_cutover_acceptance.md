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
