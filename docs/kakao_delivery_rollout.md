# Kakao delivery state: staged rollout and recovery

This feature is **not enabled**. Do not merge or apply the SQL migration until the production sender is adapted and reviewed. The existing scheduler and `morning_reports.kakao_sent_at` remain authoritative.

## Current guarantees and limits

- A successful atomic claim inserts one active attempt per user and report date. Competing claims cannot both succeed.
- A completed legacy `morning_reports.kakao_sent_at` marker blocks a new claim.
- `sent`, `uncertain`, and even an expired `sending` lease are **not** automatically retried.
- The API does **not** provide exactly-once delivery. If Kakao accepted a request but the database update fails, reconciliation is required.
- The legacy sender does not inspect `kakao_delivery_attempts`; running legacy and new senders together can still duplicate messages.
- The new claim currently checks the legacy marker without locking the legacy sender. It is **not** safe for a mixed-version rollout.

## Prerequisites before activation

1. Validate migration SQL, role grants, and integration tests on a disposable Supabase-compatible PostgreSQL instance. Confirm the production schema for `profiles` and `morning_reports` matches the SQL.
2. Implement the new sender behind a default-OFF feature flag. It must obtain and commit a claim **before** contacting Kakao, and refuse sending on a NULL claim or DB error.
3. Require one authoritative scheduler during rollout. Disable the old scheduled sender and wait for all in-flight executions to finish before enabling the new sender. Do not run both versions concurrently.
4. Preserve the existing Tuesday–Saturday Korea-time schedule and all per-user eligibility checks. Do not use manual forced sends as a test.
5. For already sent reports, respect the legacy sent marker. Backfill/audit old sent records before cutover; never mark an uncertain record as safely unsent based on elapsed time alone.
6. Test crash before request, crash after request, network timeout, DB commit timeout, expired lease, and concurrent workers. Review outcomes before enabling production sends.
7. Enable for a controlled test account first, with an explicit operator-approved rollback plan. Do not change production settings automatically.

## Recovery decision table

| State | Automatic resend | Operator action |
| --- | --- | --- |
| pending | Only after exclusive claim | Verify no previous attempt |
| failed_before_send | May claim again | Confirm no network request occurred |
| sending | Never, even if lease expired | Reconcile request and DB state |
| uncertain | Never | Verify Kakao delivery evidence; manual resolution |
| sent | Never | No action |

**Rollback:** Disable the new sender feature flag and stop new jobs. Wait for any in-flight new sender to finish. Before restoring the old sender, reconcile every `sending` and `uncertain` attempt against Kakao and the legacy sent marker; otherwise the old sender may resend. The SQL table can remain unused; do not drop records during recovery.

## Staged feature gate (not connected to sender)

`services/kakao_delivery_feature_gate.py` provides a strict default-OFF gate. Both `KAKAO_DELIVERY_STATE_ENABLED=true` and `KAKAO_DELIVERY_CUTOVER_APPROVED=true` are required; partial or misspelled values are rejected. **These flags do not yet activate a new sender**: production send code does not import the gate. Never set these flags in production before the single-scheduler cutover and sender integration have been reviewed.

## Isolated orchestration (not connected to scheduler)

`services/kakao_delivery_orchestrator.py` now models gated claim → transport → completion. It assumes `claim()` commits before returning; DB failures block transport. Transport exceptions and post-send completion failures are marked uncertain, requiring reconciliation. This is a **unit-tested skeleton**, not an operational sender: there is no real database adapter, transport binding, or scheduler integration. Do not treat its presence as production activation readiness.

## Staged end-to-end adapter (mock transport only)

`services/kakao_delivery_staged.py` composes the transactional PostgreSQL adapter with the feature-gated orchestrator. Integration tests use a mock transport to prove that successful delivery, duplicate invocations, disabled gates, and transport timeouts do not generate extra sends. It remains completely disconnected from the live Kakao sender and scheduled jobs. Setting flags alone does not switch the production path.

## Verified production integration points (code review)

- Scheduled entry point: `scripts/run_multi_user_morning_reports.py:run_all_users` calls `DailyReportService.generate_and_send(send_kakao=..., update_prices=False, force_kakao=send_kakao)` for each eligible user.
- Current same-day skip checks `Repository.get_morning_report_for_date(...).kakao_sent_at` only when not forced. The runner passes `force_kakao=True` for enabled users, so migration must review forced-send semantics separately.
- `services/daily_report_service.py:generate_and_send` performs the Kakao transport and calls `Repository.mark_morning_report_kakao_sent(report_date)` after successful delivery, with up to three retries. It logs a possible duplicate if all completion writes fail.
- Do **not** wrap the entire report generation in the new claim: generate/save report first, then claim immediately before the network send. Refactor the transport boundary to preserve HTML generation when Kakao is disabled.
- Any production integration must update both new attempt state and the legacy sent marker, with conservative reconciliation if either completion write fails. Do not automatically resend if a Kakao request may already have been accepted.
- Audit `force_kakao` and `FORCE_MORNING_REPORT`: an explicit force action must not bypass an unresolved `sending`/`uncertain` attempt. The staged integration currently does not handle manual force flows.
- Review other entry points such as CLI/manual UI calls to `DailyReportService.generate_and_send`; a cutover limited to the scheduled runner would leave mixed-version senders active.

## Common manual/scheduled/CLI eligibility policy (staged)

`services/kakao_delivery_eligibility.py` models one conservative rule for scheduled, manual, and CLI sends. A force flag can request report regeneration but **never** override a prior sent marker or any pending/sending/sent/uncertain attempt. A clean date or explicitly verified `failed_before_send` may proceed to a separate atomic DB claim. This is a unit-tested policy only, not yet connected to any live entry point. At cutover, all call sites must use this rule and a committed claim before sending.

## Kakao transport result contract

`KakaoService.send_morning_report` returns `(bool, message)`, including failures without throwing. The staged orchestrator must never interpret `(False, reason)` as success. Negative responses are conservatively classified `uncertain`, since some transport errors may occur after the server accepts the request; a definitive pre-send rejection can only be classified `failed_before_send` with explicit evidence. The production sender remains unchanged.

## Reconciliation guidance (read-only)

`services/kakao_delivery_reconciliation.py` provides operator guidance only, with no DB writes and no send calls. `uncertain` and expired `sending` require external verification of Kakao delivery; neither authorizes automatic resend. `failed_before_send` still requires confirming no request was submitted before a new claim. A legacy sent marker takes precedence. Never change an uncertain attempt to a retryable state solely because a lease expired.

## Client-role and tenant isolation checks

Disposable PostgreSQL integration tests now assert that `anon` and `authenticated` have no SELECT/INSERT/UPDATE table privileges or EXECUTE privileges on claim/finish functions, that RLS is enabled, and that independent users/dates can claim without interfering. Finalization with another user's ID must fail. These checks apply only to the disposable CI database, not production Supabase grants; verify actual production grants before any migration rollout.

## Legacy/new sent marker consistency (staged audit)

`services/kakao_delivery_marker_audit.py` compares legacy `morning_reports.kakao_sent_at` with new attempt status without changing either. A new `sent` record without a legacy sent marker, or a legacy sent marker paired with a non-sent new attempt, requires manual review. `uncertain` always requires review even when the markers do not contradict. This module is not connected to production. **Blocking rollout requirement:** the current staged `finish_kakao_delivery_attempt` updates only the new attempt table; production cutover must implement and test durable dual-marker completion or an explicitly reviewed replacement of every legacy reader before enabling live sending.

## Staged atomic dual-marker completion (not wired)

The staged migration now includes `finish_kakao_delivery_with_legacy(user_id,attempt_id)`: it locks the owned `sending` attempt, requires the dated `morning_reports` row, updates the legacy sent timestamp, and marks the new attempt `sent` in the same PostgreSQL transaction. A missing legacy row returns false without updating either marker. Disposable PostgreSQL tests cover both paths. **Cutover remains blocked** until the staged sender uses this function on success (rather than the single-marker finish method), other send entry points are coordinated, and production schema/grants are verified. Do not apply this migration yet.

## Staged sender now uses dual-marker completion

`run_staged_delivery` now calls `PostgresDeliveryAttempts.finish_sent_with_legacy` on transport success; only an uncertain transport outcome uses the separate single-attempt finalizer. The disposable integration test creates the dated report first and verifies the legacy marker is populated. This staged code is still **not imported or invoked by the live scheduler**, and does not authorize a production cutover.
