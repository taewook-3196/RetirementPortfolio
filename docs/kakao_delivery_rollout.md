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
