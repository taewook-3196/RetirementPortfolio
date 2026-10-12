"""Contract checks for the staged KakaoService adapter; no real Kakao calls."""
from datetime import date
from unittest.mock import patch

import pytest
from uuid import uuid4

from services.kakao_delivery_orchestrator import SendOutcome
from services.kakao_delivery_transport_adapter import send_staged_morning_report


class FakeKakaoService:
    def __init__(self):
        self.calls = []

    def send_morning_report(self, summary_text, report_web_url):
        self.calls.append((summary_text, report_web_url))
        return True, "ok"


def test_adapter_passes_existing_kakao_arguments_only_through_claimed_transport():
    fake = FakeKakaoService()
    captured = {}

    def staged(**kwargs):
        captured.update(kwargs)
        return kwargs["transport"]()

    with patch("services.kakao_delivery_transport_adapter.run_staged_delivery", side_effect=staged):
        result = send_staged_morning_report(
            engine=object(), user_id=uuid4(), report_date=date(2026, 10, 12),
            kakao_service=fake, summary_text="test summary", report_web_url="https://example.com/report",
            env={},
        )
    assert result == (True, "ok")
    assert fake.calls == [("test summary", "https://example.com/report")]
    assert callable(captured["transport"])


def test_adapter_does_not_send_when_staged_claim_is_denied():
    fake = FakeKakaoService()

    def staged(**kwargs):
        return SendOutcome.NOT_CLAIMED

    with patch("services.kakao_delivery_transport_adapter.run_staged_delivery", side_effect=staged):
        result = send_staged_morning_report(
            engine=object(), user_id=uuid4(), report_date=date(2026, 10, 12),
            kakao_service=fake, summary_text="test", report_web_url="https://example.com",
        )
    assert result == SendOutcome.NOT_CLAIMED
    assert fake.calls == []


def test_adapter_default_off_gate_never_calls_kakao_transport():
    from services.kakao_delivery_orchestrator import SendResult

    fake = FakeKakaoService()
    with patch("services.kakao_delivery_staged.PostgresDeliveryAttempts") as store:
        result = send_staged_morning_report(
            engine=object(), user_id=uuid4(), report_date=date(2026, 10, 12),
            kakao_service=fake, summary_text="test", report_web_url="https://example.com",
            env={},
        )
    assert isinstance(result, SendResult)
    assert result.outcome == SendOutcome.DISABLED
    assert fake.calls == []
    store.return_value.claim.assert_not_called()


@pytest.mark.parametrize("env", [
    {"KAKAO_DELIVERY_STATE_ENABLED": "true"},
    {"KAKAO_DELIVERY_CUTOVER_APPROVED": "true"},
    {"KAKAO_DELIVERY_STATE_ENABLED": "TRUE", "KAKAO_DELIVERY_CUTOVER_APPROVED": "true"},
    {"KAKAO_DELIVERY_STATE_ENABLED": "true", "KAKAO_DELIVERY_CUTOVER_APPROVED": "TRUE"},
])
def test_adapter_partial_or_inexact_feature_gate_cannot_send(env):
    from services.kakao_delivery_orchestrator import SendResult

    fake = FakeKakaoService()
    with patch("services.kakao_delivery_staged.PostgresDeliveryAttempts") as store:
        result = send_staged_morning_report(
            engine=object(), user_id=uuid4(), report_date=date(2026, 10, 12),
            kakao_service=fake, summary_text="test", report_web_url="https://example.com",
            env=env,
        )
    assert isinstance(result, SendResult)
    assert result.outcome == SendOutcome.DISABLED
    assert fake.calls == []
    store.return_value.claim.assert_not_called()
