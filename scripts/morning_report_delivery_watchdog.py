"""Read-only morning-report delivery watchdog core.

An independent scheduler can invoke this logic after 09:00 KST.
No send, resend, database mutation, or public unauthenticated endpoint.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from scripts.audit_morning_report_schedule import audit_runs, expected_slots

SEOUL = ZoneInfo("Asia/Seoul")


def evaluate_delivery(
    day: dt.date,
    now: dt.datetime,
    runs: list[dict],
    recipients: list[dict],
) -> dict:
    """Evaluate *pre-fetched* recipient statuses without exposing identities.

    recipients: [{enabled: bool, kakao_enabled: bool,
                  sent_at: ISO timestamp or None}]
    Caller must fetch recipient status using an authorized, read-only
    database connection. This function never queries the DB itself.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    local_now = now.astimezone(SEOUL)
    schedule = audit_runs(day, runs)
    if not expected_slots(day):
        state = "not_scheduled_day"
    elif local_now.date() < day or (local_now.date() == day and local_now.time() < dt.time(9, 30)):
        state = "awaiting_cutoff"
    elif local_now.date() > day:
        state = "historical_audit"
    else:
        state = "ready"

    eligible = 0
    delivered = 0
    missing = 0
    for recipient in recipients:
        if not recipient.get("enabled") or not recipient.get("kakao_enabled"):
            continue
        eligible += 1
        stamp = recipient.get("sent_at")
        sent_today = recipient.get("report_date_marker_present") is True
        if stamp:
            try:
                parsed = dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
                sent_today = parsed.tzinfo is not None and parsed.astimezone(SEOUL).date() == day
            except (TypeError, ValueError, OverflowError):
                sent_today = False
        if sent_today:
            delivered += 1
        else:
            missing += 1

    if state == "ready":
        if missing:
            diagnosis = "delivery_marker_missing"
        elif schedule["schedule_missing"]:
            diagnosis = "schedule_missing_but_delivery_markers_complete"
        else:
            diagnosis = "no_missing_delivery_markers"
    else:
        diagnosis = state
    return {
        "date_kst": day.isoformat(),
        "diagnosis": diagnosis,
        "scheduled_run_diagnosis": schedule["diagnosis"],
        "eligible_recipient_count": eligible,
        "delivered_marker_count": delivered,
        "missing_marker_count": missing,
        "note": "Marker absence is not proof of non-delivery; do not auto-resend.",
    }
