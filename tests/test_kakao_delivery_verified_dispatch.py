"""Staged-only verified dispatcher contract; no real Kakao calls."""
from datetime import date
from unittest.mock import Mock
from uuid import uuid4

import pytest

from services.kakao_delivery_eligibility import DeliveryOrigin
from services.kakao_delivery_orchestrator import SendOutcome, SendResult
from services.kakao_delivery_verified_dispatch import dispatch_verified_staged_report

ENABLED = {
    "KAKAO_DELIVERY_STATE_ENABLED": "true",
    "KAKAO_DELIVERY_CUTOVER_APPROVED": "true",
}


def args(**overrides):
    values = dict(
        origin=DeliveryOrigin.SCHEDULED, engine=object(), user_id=uuid4(),
        report_date=date(2026, 10, 14), kakao_service=object(),
        summary_text="summary", report_web_url="https://example.com/report",
        force=False, env=ENABLED,
    )
    values.update(overrides)
    return values


@pytest.mark.parametrize("overrides", [
    {"origin": "scheduled"}, {"force": None}, {"force": 1},
    {"user_id": None}, {"user_id": "unknown"},
    {"report_date": None}, {"report_date": "2026-10-14"},
    {"summary_text": None}, {"summary_text": "  "},
    {"report_web_url": None}, {"report_web_url": ""},
])
def test_invalid_dispatch_inputs_never_touch_db_or_provider(monkeypatch, overrides):
    preflight = Mock(side_effect=AssertionError("unexpected database read"))
    gateway = Mock(side_effect=AssertionError("unexpected send"))
    monkeypatch.setattr(
        "services.kakao_delivery_verified_dispatch.verify_cached_report_identity", preflight
    )
    monkeypatch.setattr(
        "services.kakao_delivery_verified_dispatch.send_staged_for_origin", gateway
    )
    result = dispatch_verified_staged_report(**args(**overrides))
    assert result.outcome == SendOutcome.NOT_CLAIMED
    preflight.assert_not_called()
    gateway.assert_not_called()


def test_disabled_dispatch_never_reads_database(monkeypatch):
    preflight = Mock(side_effect=AssertionError("unexpected database read"))
    monkeypatch.setattr(
        "services.kakao_delivery_verified_dispatch.verify_cached_report_identity", preflight
    )
    assert dispatch_verified_staged_report(**args(env={})).outcome == SendOutcome.DISABLED
    preflight.assert_not_called()


def test_database_read_error_propagates_without_fallback_send(monkeypatch):
    preflight = Mock(side_effect=RuntimeError("database unavailable"))
    gateway = Mock(side_effect=AssertionError("must not send"))
    monkeypatch.setattr(
        "services.kakao_delivery_verified_dispatch.verify_cached_report_identity", preflight
    )
    monkeypatch.setattr(
        "services.kakao_delivery_verified_dispatch.send_staged_for_origin", gateway
    )
    with pytest.raises(RuntimeError, match="database unavailable"):
        dispatch_verified_staged_report(**args())
    gateway.assert_not_called()


@pytest.mark.parametrize("origin", list(DeliveryOrigin))
def test_all_origins_forward_verified_identity_and_state(monkeypatch, origin):
    identity = Mock(user_id=uuid4(), report_date=date(2026, 10, 14),
                    legacy_sent=True, attempt_state="uncertain")
    monkeypatch.setattr(
        "services.kakao_delivery_verified_dispatch.verify_cached_report_identity",
        Mock(return_value=identity),
    )
    gateway = Mock(return_value=SendResult(SendOutcome.NOT_CLAIMED))
    monkeypatch.setattr(
        "services.kakao_delivery_verified_dispatch.send_staged_for_origin", gateway
    )
    result = dispatch_verified_staged_report(**args(origin=origin, force=True))
    assert result.outcome == SendOutcome.NOT_CLAIMED
    assert gateway.call_args.kwargs["origin"] == origin
    assert gateway.call_args.kwargs["user_id"] == identity.user_id
    assert gateway.call_args.kwargs["legacy_sent"] is True
    assert gateway.call_args.kwargs["attempt_state"] == "uncertain"
