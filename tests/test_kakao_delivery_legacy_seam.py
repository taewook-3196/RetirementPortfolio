"""Regression coverage for isolated live legacy sender (no network calls)."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

from services.daily_report_service import DailyReportService


def service_with_mocks(*, provider=(True, "mock"), marker=True, user_id="user"):
    service = DailyReportService.__new__(DailyReportService)
    service.kakao_service = SimpleNamespace(send_morning_report=Mock(return_value=provider))
    service.repo = SimpleNamespace(
        user_id=user_id, mark_morning_report_kakao_sent=Mock(return_value=marker)
    )
    return service


def test_legacy_sender_records_only_after_provider_success():
    service = service_with_mocks()
    result = service._send_legacy_report_and_record(
        report_date=date(2026, 10, 15),
        summary_text="summary", report_web_url="https://example.com/report",
    )
    assert result[0] is True
    service.kakao_service.send_morning_report.assert_called_once()
    service.repo.mark_morning_report_kakao_sent.assert_called_once_with(date(2026, 10, 15))


def test_legacy_sender_provider_failure_does_not_mark_sent():
    service = service_with_mocks(provider=(False, "provider failed"))
    ok, message = service._send_legacy_report_and_record(
        report_date=date(2026, 10, 15),
        summary_text="summary", report_web_url="https://example.com/report",
    )
    assert not ok
    assert "provider failed" in message
    service.repo.mark_morning_report_kakao_sent.assert_not_called()


def test_legacy_sender_marker_failure_returns_warning_without_resending():
    service = service_with_mocks(marker=False)
    with patch("services.daily_report_service.time.sleep"):
        ok, message = service._send_legacy_report_and_record(
            report_date=date(2026, 10, 15),
            summary_text="summary", report_web_url="https://example.com/report",
        )
    assert not ok
    assert "중복 발송" in message
    assert service.repo.mark_morning_report_kakao_sent.call_count == 3
    service.kakao_service.send_morning_report.assert_called_once()


def test_legacy_sender_without_user_preserves_existing_behavior():
    service = service_with_mocks(user_id=None)
    ok, _ = service._send_legacy_report_and_record(
        report_date=date(2026, 10, 15),
        summary_text="summary", report_web_url="https://example.com/report",
    )
    assert ok
    service.repo.mark_morning_report_kakao_sent.assert_not_called()


def test_dormant_staged_report_method_delegates_without_legacy_send():
    from uuid import uuid4
    from services.kakao_delivery_eligibility import DeliveryOrigin
    from services.kakao_delivery_orchestrator import SendOutcome
    from services.kakao_delivery_report_bridge import ReportDeliveryResult

    service = service_with_mocks()
    user_id = uuid4()
    staged = Mock(return_value=ReportDeliveryResult(
        False, "발송 권한 없음", SendOutcome.NOT_CLAIMED,
    ))
    with patch(
        "services.kakao_delivery_report_bridge.send_persisted_report_staged",
        staged,
    ):
        ok, message = service._send_verified_report_staged(
            engine=object(), origin=DeliveryOrigin.MANUAL,
            user_id=user_id, report_date=date(2026, 10, 15),
            summary_text="summary", report_web_url="https://example.com/report",
            force=True,
        )
    assert not ok
    assert message == "발송 권한 없음"
    assert staged.call_args.kwargs["user_id"] == user_id
    assert staged.call_args.kwargs["origin"] is DeliveryOrigin.MANUAL
    assert staged.call_args.kwargs["kakao_service"] is service.kakao_service
    service.kakao_service.send_morning_report.assert_not_called()
    service.repo.mark_morning_report_kakao_sent.assert_not_called()


def test_live_report_sender_still_calls_only_legacy_method():
    from pathlib import Path

    source = Path("services/daily_report_service.py").read_text(encoding="utf-8")
    live_section = source.split("            # 6. 카카오톡 메시지 전송", 1)[1].split(
        "    def _send_verified_report_staged(", 1
    )[0]
    assert "self._send_legacy_report_and_record(" in live_section
    assert "self._send_verified_report_staged(" not in live_section
