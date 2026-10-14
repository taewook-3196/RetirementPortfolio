"""Staged-only delivery gateway contracts; no Kakao HTTP or production sender."""
from datetime import date
from uuid import uuid4

import pytest

from services.kakao_delivery_orchestrator import SendOutcome
from services.kakao_delivery_staged import run_staged_delivery

ON = {"KAKAO_DELIVERY_STATE_ENABLED": "true", "KAKAO_DELIVERY_CUTOVER_APPROVED": "true"}


@pytest.mark.parametrize("origin", ["scheduled", "manual", "cli", "cached"])
def test_staged_gateway_never_transports_when_claim_denied(monkeypatch, origin):
    events = []

    class FakeStore:
        def __init__(self, engine):
            assert engine is None

        def claim(self, attempt):
            events.append((origin, "claim"))
            return None

        def finish_sent_with_legacy(self, attempt):
            pytest.fail("finish must not run")

        def finish(self, attempt, status):
            pytest.fail("finish must not run")

    monkeypatch.setattr("services.kakao_delivery_staged.PostgresDeliveryAttempts", FakeStore)
    result = run_staged_delivery(
        engine=None, user_id=uuid4(), report_date=date(2026, 10, 14),
        transport=lambda: pytest.fail("Kakao transport bypassed durable claim"), env=ON,
    )
    assert result.outcome == SendOutcome.NOT_CLAIMED
    assert events == [(origin, "claim")]


def test_staged_gateway_disabled_flags_do_not_claim_or_send(monkeypatch):
    class ForbiddenStore:
        def __init__(self, engine):
            pytest.fail("disabled gateway initialized database adapter")

    monkeypatch.setattr("services.kakao_delivery_staged.PostgresDeliveryAttempts", ForbiddenStore)
    result = run_staged_delivery(
        engine=None, user_id=uuid4(), report_date=date(2026, 10, 14),
        transport=lambda: pytest.fail("disabled gateway sent Kakao"), env={},
    )
    assert result.outcome == SendOutcome.DISABLED


@pytest.mark.parametrize("response", [(True, "accepted"), (False, "timeout")])
def test_staged_gateway_claims_before_transport_and_finishes(monkeypatch, response):
    events = []

    class FakeStore:
        def __init__(self, engine):
            pass

        def claim(self, attempt):
            events.append("claim")
            return 42

        def finish_sent_with_legacy(self, attempt):
            events.append("sent")
            return True

        def finish(self, attempt, status):
            events.append(status)
            return True

    monkeypatch.setattr("services.kakao_delivery_staged.PostgresDeliveryAttempts", FakeStore)
    result = run_staged_delivery(
        engine=None, user_id=uuid4(), report_date=date(2026, 10, 14),
        transport=lambda: events.append("transport") or response, env=ON,
    )
    assert events == ["claim", "transport", "sent" if response[0] else "uncertain"]
    assert result.outcome == (SendOutcome.SENT if response[0] else SendOutcome.UNCERTAIN)
