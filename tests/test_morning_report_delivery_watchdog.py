import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from scripts.morning_report_delivery_watchdog import evaluate_delivery

KST = ZoneInfo("Asia/Seoul")
DAY = dt.date(2026, 10, 13)


def _check(hour, recipients, runs=None):
    return evaluate_delivery(DAY, dt.datetime(2026, 10, 13, hour, 30, tzinfo=KST), runs or [], recipients)


def test_waits_until_after_final_backup_slot():
    result = evaluate_delivery(DAY, dt.datetime(2026, 10, 13, 9, 15, tzinfo=KST), [], [])
    assert result["diagnosis"] == "awaiting_cutoff"


def test_missing_delivery_marker_is_not_resend_instruction():
    result = _check(10, [{"enabled": True, "kakao_enabled": True, "sent_at": None}])
    assert result["diagnosis"] == "delivery_marker_missing"
    assert result["missing_marker_count"] == 1
    assert "resend" in result["note"]


def test_disabled_users_are_not_reported_missing():
    result = _check(10, [
        {"enabled": False, "kakao_enabled": True, "sent_at": None},
        {"enabled": True, "kakao_enabled": False, "sent_at": None},
    ])
    assert result["eligible_recipient_count"] == 0
    assert result["missing_marker_count"] == 0


def test_success_marker_does_not_claim_scheduled_run_existed():
    result = _check(10, [{"enabled": True, "kakao_enabled": True, "sent_at": "2026-10-13T00:51:00Z"}])
    assert result["diagnosis"] == "schedule_missing_but_delivery_markers_complete"
    assert result["delivered_marker_count"] == 1


def test_previous_day_marker_not_accepted():
    result = _check(10, [{"enabled": True, "kakao_enabled": True, "sent_at": "2026-10-12T00:51:00Z"}])
    assert result["missing_marker_count"] == 1


def test_naive_clock_rejected():
    with pytest.raises(ValueError):
        evaluate_delivery(DAY, dt.datetime(2026, 10, 13, 10, 30), [], [])
