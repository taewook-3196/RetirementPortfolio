from datetime import date
from uuid import uuid4
from unittest.mock import Mock

import pytest

from services.kakao_delivery_eligibility import DeliveryOrigin
from services.kakao_delivery_orchestrator import SendOutcome, SendResult
from services.kakao_delivery_origin_gateway import send_staged_for_origin


ENABLED = {
    "KAKAO_DELIVERY_STATE_ENABLED": "true",
    "KAKAO_DELIVERY_CUTOVER_APPROVED": "true",
}


@pytest.mark.parametrize("origin", list(DeliveryOrigin))
@pytest.mark.parametrize("force", [False, True])
def test_all_origins_reach_same_staged_adapter_only_when_eligible(monkeypatch, origin, force):
    adapter = Mock(return_value=SendResult(SendOutcome.NOT_CLAIMED))
    monkeypatch.setattr(
        "services.kakao_delivery_origin_gateway.send_staged_morning_report", adapter
    )
    result = send_staged_for_origin(
        origin=origin, engine=object(), user_id=uuid4(), report_date=date(2026, 10, 14),
        kakao_service=object(), summary_text="summary", report_web_url="https://example.com",
        legacy_sent=False, attempt_state=None, force=force, env=ENABLED,
    )
    assert result.outcome == SendOutcome.NOT_CLAIMED
    adapter.assert_called_once()


@pytest.mark.parametrize("origin", list(DeliveryOrigin))
@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("state", ["sending", "sent", "uncertain", "failed_before_send"])
def test_existing_attempt_never_reaches_adapter(monkeypatch, origin, force, state):
    adapter = Mock()
    monkeypatch.setattr(
        "services.kakao_delivery_origin_gateway.send_staged_morning_report", adapter
    )
    result = send_staged_for_origin(
        origin=origin, engine=None, user_id=uuid4(), report_date=date(2026, 10, 14),
        kakao_service=None, summary_text="", report_web_url="",
        legacy_sent=False, attempt_state=state, force=force, env=ENABLED,
    )
    assert result.outcome == SendOutcome.NOT_CLAIMED
    adapter.assert_not_called()


@pytest.mark.parametrize("origin", list(DeliveryOrigin))
def test_legacy_sent_never_reaches_adapter(monkeypatch, origin):
    adapter = Mock()
    monkeypatch.setattr(
        "services.kakao_delivery_origin_gateway.send_staged_morning_report", adapter
    )
    result = send_staged_for_origin(
        origin=origin, engine=None, user_id=uuid4(), report_date=date(2026, 10, 14),
        kakao_service=None, summary_text="", report_web_url="",
        legacy_sent=True, attempt_state=None, force=True, env=ENABLED,
    )
    assert result.outcome == SendOutcome.NOT_CLAIMED
    adapter.assert_not_called()


def test_disabled_gate_does_not_even_inspect_origin_or_service(monkeypatch):
    adapter = Mock()
    monkeypatch.setattr(
        "services.kakao_delivery_origin_gateway.send_staged_morning_report", adapter
    )
    result = send_staged_for_origin(
        origin="unknown", engine=None, user_id=None, report_date=None,
        kakao_service=None, summary_text="", report_web_url="",
        legacy_sent=None, attempt_state=None, env={},
    )
    assert result.outcome == SendOutcome.DISABLED
    adapter.assert_not_called()


def test_unknown_origin_fails_closed(monkeypatch):
    adapter = Mock()
    monkeypatch.setattr(
        "services.kakao_delivery_origin_gateway.send_staged_morning_report", adapter
    )
    result = send_staged_for_origin(
        origin="cli", engine=None, user_id=None, report_date=None,
        kakao_service=None, summary_text="", report_web_url="",
        legacy_sent=False, attempt_state=None, env=ENABLED,
    )
    assert result.outcome == SendOutcome.NOT_CLAIMED
    adapter.assert_not_called()


@pytest.mark.parametrize("overrides", [
    {"user_id": None},
    {"user_id": "not-a-uuid"},
    {"report_date": None},
    {"report_date": "2026-10-14"},
    {"summary_text": None},
    {"summary_text": "  "},
    {"report_web_url": None},
    {"report_web_url": "http://example.com"},
    {"report_web_url": "javascript:alert(1)"},
])
def test_invalid_identity_or_payload_never_reaches_adapter(monkeypatch, overrides):
    adapter = Mock()
    monkeypatch.setattr(
        "services.kakao_delivery_origin_gateway.send_staged_morning_report", adapter
    )
    args = dict(
        origin=DeliveryOrigin.SCHEDULED, engine=object(), user_id=uuid4(),
        report_date=date(2026, 10, 14), kakao_service=object(),
        summary_text="summary", report_web_url="https://example.com",
        legacy_sent=False, attempt_state=None, env=ENABLED,
    )
    args.update(overrides)
    result = send_staged_for_origin(**args)
    assert result.outcome == SendOutcome.NOT_CLAIMED
    adapter.assert_not_called()


@pytest.mark.parametrize("origin", list(DeliveryOrigin))
def test_untrusted_caller_hint_cannot_authorize_transport_when_claim_denied(monkeypatch, origin):
    from services.kakao_delivery_staged import run_staged_delivery

    class DeniedStore:
        def __init__(self, engine):
            pass

        def claim(self, attempt):
            return None

        def finish(self, attempt, status):
            pytest.fail("denied claim must not finish")

        def finish_sent_with_legacy(self, attempt):
            pytest.fail("denied claim must not finalize")

    class Service:
        def is_configured(self):
            return True

        def send_morning_report(self, summary, url):
            pytest.fail("caller hints must not bypass committed DB claim")

    monkeypatch.setattr("services.kakao_delivery_staged.PostgresDeliveryAttempts", DeniedStore)
    result = send_staged_for_origin(
        origin=origin, engine=object(), user_id=uuid4(),
        report_date=date(2026, 10, 14), kakao_service=Service(),
        summary_text="summary", report_web_url="https://example.com",
        legacy_sent=False, attempt_state=None, force=True, env=ENABLED,
    )
    assert result.outcome == SendOutcome.NOT_CLAIMED
