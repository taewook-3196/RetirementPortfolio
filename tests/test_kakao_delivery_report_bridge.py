"""Report service staged bridge outcomes never trigger legacy Kakao fallback."""
from datetime import date
from unittest.mock import Mock
from uuid import uuid4

import pytest

from services.kakao_delivery_eligibility import DeliveryOrigin
from services.kakao_delivery_orchestrator import SendOutcome, SendResult
from services.kakao_delivery_report_bridge import send_persisted_report_staged


@pytest.mark.parametrize("outcome,expected_ok", [
    (SendOutcome.SENT, True),
    (SendOutcome.UNCERTAIN, False),
    (SendOutcome.NOT_CLAIMED, False),
    (SendOutcome.DISABLED, False),
    (SendOutcome.FAILED_BEFORE_SEND, False),
])
@pytest.mark.parametrize("origin", list(DeliveryOrigin))
def test_staged_bridge_maps_all_outcomes_without_legacy_fallback(
    monkeypatch, outcome, expected_ok, origin
):
    dispatcher = Mock(return_value=SendResult(outcome))
    monkeypatch.setattr(
        "services.kakao_delivery_report_bridge.dispatch_verified_staged_report",
        dispatcher,
    )
    kakao = Mock()
    user_id = uuid4()
    report_date = date(2026, 10, 15)
    result = send_persisted_report_staged(
        origin=origin, engine=object(), user_id=user_id,
        report_date=report_date, kakao_service=kakao,
        summary_text="summary", report_web_url="https://example.com/report",
        force=True,
    )
    assert result.ok is expected_ok
    assert result.outcome is outcome
    assert dispatcher.call_args.kwargs["origin"] is origin
    assert dispatcher.call_args.kwargs["user_id"] == user_id
    assert dispatcher.call_args.kwargs["report_date"] == report_date
    assert dispatcher.call_args.kwargs["force"] is True
    kakao.send_morning_report.assert_not_called()
    if outcome is SendOutcome.UNCERTAIN:
        assert "자동 재발송하지" in result.message
