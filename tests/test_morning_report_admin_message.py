from scripts.morning_report_admin_message import format_admin_alert


def audit(diagnosis, scheduled="scheduled_run_succeeded_delivery_unverified"):
    return {
        "date_kst": "2026-10-13",
        "diagnosis": diagnosis,
        "scheduled_run_diagnosis": scheduled,
        "eligible_recipient_count": 12,
        "missing_marker_count": 3,
        "user_id": "PRIVATE_USER_ID",
        "account_balance": "PRIVATE_BALANCE",
    }


def test_no_message_when_healthy():
    assert format_admin_alert(audit("no_missing_delivery_markers")) is None


def test_missing_marker_message_is_private():
    msg = format_admin_alert(audit("delivery_marker_missing", "no_scheduled_runs"))
    assert "발송 완료 기록" in msg
    assert "예약 실행 기록 없음" in msg
    assert "PRIVATE_USER_ID" not in msg
    assert "PRIVATE_BALANCE" not in msg
    assert "자동 재발송은 실행하지 않았습니다" in msg


def test_manual_recovery_message():
    msg = format_admin_alert(
        audit("schedule_missing_manual_run_present_delivery_markers_complete", "no_scheduled_runs")
    )
    assert "수동 복구" in msg
