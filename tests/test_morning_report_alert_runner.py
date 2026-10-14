import pytest

from scripts.morning_report_alert_runner import process_admin_alert


def audit(diagnosis):
    return {
        "date_kst": "2026-10-13",
        "diagnosis": diagnosis,
        "scheduled_run_diagnosis": "no_scheduled_runs",
    }


def test_healthy_audit_does_not_send(tmp_path):
    messages = []
    result = {
        **audit("no_missing_delivery_markers"),
        "scheduled_run_diagnosis": "scheduled_run_succeeded_delivery_unverified",
    }
    assert process_admin_alert(result, store_directory=tmp_path, send=messages.append) == "skipped"
    assert not messages


def test_alert_is_sent_once(tmp_path):
    messages = []
    assert process_admin_alert(audit("delivery_marker_missing"), store_directory=tmp_path, send=messages.append) == "sent"
    assert process_admin_alert(audit("delivery_marker_missing"), store_directory=tmp_path, send=messages.append) == "duplicate"
    assert len(messages) == 1


def test_unknown_send_failure_keeps_claim_to_prevent_duplicate(tmp_path):
    def failed_send(message):
        raise ConnectionError("unknown delivery state")

    with pytest.raises(ConnectionError):
        process_admin_alert(audit("delivery_marker_missing"), store_directory=tmp_path, send=failed_send)
    messages = []
    assert process_admin_alert(audit("delivery_marker_missing"), store_directory=tmp_path, send=messages.append) == "duplicate"
    assert messages == []
