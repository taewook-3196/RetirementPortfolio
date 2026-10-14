from scripts.morning_report_admin_alert import classify_admin_alert


def result(diagnosis, scheduled="scheduled_run_succeeded_delivery_unverified", day="2026-10-13"):
    return {
        "date_kst": day,
        "diagnosis": diagnosis,
        "scheduled_run_diagnosis": scheduled,
        "missing_marker_count": 0,
    }


def test_healthy_status_does_not_alert():
    assert not classify_admin_alert(result("no_missing_delivery_markers"))["should_alert"]


def test_before_cutoff_does_not_alert_even_when_schedule_missing():
    assert not classify_admin_alert(result("awaiting_cutoff", "no_scheduled_runs"))["should_alert"]


def test_missing_delivery_marker_has_stable_dedup_key():
    first = classify_admin_alert(result("delivery_marker_missing"))
    second = classify_admin_alert(result("delivery_marker_missing"))
    assert first["should_alert"]
    assert first["dedup_key"] == second["dedup_key"]
    assert len(first["dedup_key"]) == 24


def test_new_date_generates_new_dedup_key():
    first = classify_admin_alert(result("delivery_marker_missing"))
    next_day = classify_admin_alert(result("delivery_marker_missing", day="2026-10-14"))
    assert first["dedup_key"] != next_day["dedup_key"]


def test_schedule_failure_alerts_even_when_markers_are_complete():
    alert = classify_admin_alert(result("no_missing_delivery_markers", "scheduled_runs_completed_without_success"))
    assert alert["should_alert"]


def test_manual_recovery_still_alerts_about_scheduler():
    alert = classify_admin_alert(result("schedule_missing_manual_run_present_delivery_markers_complete", "no_scheduled_runs"))
    assert alert["should_alert"]
