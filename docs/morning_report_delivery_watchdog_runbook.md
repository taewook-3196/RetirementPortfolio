# Morning report delivery watchdog — operational runbook

Status: **not deployed / not scheduled / no notifications enabled**.

## Why this exists

GitHub Actions scheduled events may be delayed or skipped. A successful
manual run does not prove the scheduled event ran, and a green workflow does
not prove that a Kakao message was sent.

The watchdog must execute **outside GitHub Actions** to detect a complete
GitHub scheduler outage. Running the watchdog as another GitHub Actions
schedule is not independent monitoring.

## Existing implementation

- `scripts.audit_morning_report_schedule`: reads workflow-run metadata
  from GitHub and distinguishes scheduled from manual runs.
- `scripts.morning_report_delivery_reader`: reads active subscribers'
  per-day delivery markers from the configured database.
- `scripts.morning_report_delivery_watchdog`: computes aggregate statuses
  without user identifiers.
- `scripts.run_morning_report_delivery_audit`: read-only CLI, with
  nonzero exit codes for review or unavailable data.

Example for an **authorized** environment with the repository dependencies,
read-only database access and optional GitHub token:

```sh
python -m scripts.run_morning_report_delivery_audit --date 2026-10-13
```

Do not paste database URLs, access tokens or recipient details into public
workflow logs or support tickets.

## Interpretation

- `awaiting_cutoff`: no final judgment before 09:30 KST.
- `not_scheduled_day`: Sunday or Monday; no routine morning delivery.
- `no_eligible_recipients_verify_configuration`: investigate settings,
  subscriber count and DB connectivity before treating it as healthy.
- `delivery_marker_missing`: review the recipient's delivery state;
  **never infer that the message was not received**.
- `schedule_missing_manual_run_present_delivery_markers_complete`:
  manual recovery succeeded, but scheduled execution still needs attention.
- `scheduled_runs_completed_without_success`: workflow failure; inspect
  run logs, do not resend automatically.
- `scheduled_run_in_progress`: wait or inspect a delayed run.
- `no_missing_delivery_markers`: all eligible recipients have DB markers,
  but this is not independent proof of delivery.

## Deployment prerequisites (not completed)

1. Choose and authorize an **independent scheduler** with a stable 09:30 KST
   or later trigger and suitable reliability; verify its price before setup.
2. Provide only the necessary read-only database access and GitHub Actions
   read access. Never embed secrets in repository source.
3. Select an administrator-only alert channel. Avoid posting recipient data.
4. Test with a fake DB and mocked GitHub API first; then verify production
   read-only queries without triggering any sends.
5. Implement deduplicated alerts and retry/backoff for temporary API failures.
6. Document a manual incident procedure and owner acknowledgement.
7. Explicitly approve deployment and recurring scheduling before enabling.

## Operational safety

No code in this PR sends Kakao messages, changes scheduled cron expressions,
or mutates production database records. A failure to query the GitHub API
or database must be treated as an **unknown/unavailable** result, not healthy.

Do not automatically re-send a report when the delivery marker is missing:
Kakao may have accepted the message even if the marker update failed.

A Render free web service can sleep and should not be assumed to provide a
reliable internal timer. Creating a Render Cron Job or any paid service
requires separate approval after cost review.
