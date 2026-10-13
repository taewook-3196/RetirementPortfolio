"""Pure administrator alert classification for morning-report audits.

No network access, recipient identifiers, or outbound messages.
An independent runner must persist the deduplication key before alerting.
"""
from __future__ import annotations

import hashlib


REVIEW_STATES = frozenset({
    "no_eligible_recipients_verify_configuration",
    "delivery_marker_missing",
    "schedule_missing_manual_run_present_delivery_markers_complete",
    "schedule_missing_but_delivery_markers_complete",
})
SCHEDULE_REVIEW_STATES = frozenset({
    "no_scheduled_runs",
    "scheduled_runs_completed_without_success",
    "scheduled_run_in_progress",
})


def classify_admin_alert(result: dict) -> dict:
    """Return a stable, non-sensitive alert descriptor or a no-alert result."""
    diagnosis = str(result["diagnosis"])
    scheduled = str(result["scheduled_run_diagnosis"])
    day = str(result["date_kst"])
    if diagnosis in {"awaiting_cutoff", "historical_audit", "not_scheduled_day"}:
        return {"should_alert": False, "reason": "outside_active_audit_window"}
    reasons = []
    if diagnosis in REVIEW_STATES:
        reasons.append(diagnosis)
    if scheduled in SCHEDULE_REVIEW_STATES:
        reasons.append(scheduled)
    if not reasons:
        return {"should_alert": False, "reason": "no_review_needed"}
    # A date+reason fingerprint prevents repeat notifications for the same
    # finding; persistence and atomic deduplication belong to the runner.
    signature = "|".join([day, *sorted(set(reasons))])
    return {
        "should_alert": True,
        "reason": ",".join(sorted(set(reasons))),
        "dedup_key": hashlib.sha256(signature.encode("utf-8")).hexdigest()[:24],
        "date_kst": day,
    }
