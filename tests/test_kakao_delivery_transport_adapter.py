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

    def is_configured(self):
        return True

    def send_morning_report(self, summary_text, report_web_url):
        self.calls.append((summary_text, report_web_url))
        return True, "ok"


def test_adapter_passes_existing_kakao_arguments_only_after_durable_claim():
    fake = FakeKakaoService()
    env = {"KAKAO_DELIVERY_STATE_ENABLED": "true", "KAKAO_DELIVERY_CUTOVER_APPROVED": "true"}
    with patch("services.kakao_delivery_staged.PostgresDeliveryAttempts") as store_class:
        store = store_class.return_value
        store.claim.return_value = uuid4()
        store.finish_sent_with_legacy.return_value = True
        result = send_staged_morning_report(
            engine=object(), user_id=uuid4(), report_date=date(2026, 10, 12),
            kakao_service=fake, summary_text="test summary",
            report_web_url="https://example.com/report", env=env,
        )
        store.claim.assert_called_once()
        store.finish_sent_with_legacy.assert_called_once()
    assert result.outcome == SendOutcome.SENT
    assert fake.calls == [("test summary", "https://example.com/report")]


def test_adapter_does_not_send_when_staged_claim_is_denied():
    fake = FakeKakaoService()
    env = {"KAKAO_DELIVERY_STATE_ENABLED": "true", "KAKAO_DELIVERY_CUTOVER_APPROVED": "true"}
    with patch("services.kakao_delivery_staged.PostgresDeliveryAttempts") as store_class:
        store = store_class.return_value
        store.claim.return_value = None
        result = send_staged_morning_report(
            engine=object(), user_id=uuid4(), report_date=date(2026, 10, 12),
            kakao_service=fake, summary_text="test", report_web_url="https://example.com",
            env=env,
        )
        store.claim.assert_called_once()
        store.finish.assert_not_called()
        store.finish_sent_with_legacy.assert_not_called()
    assert result.outcome == SendOutcome.NOT_CLAIMED
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


@pytest.mark.parametrize("legacy_finalize_ok, expected", [
    (True, SendOutcome.SENT),
    (False, SendOutcome.UNCERTAIN),
])
def test_adapter_real_staged_orchestrator_uses_atomic_legacy_finalizer(legacy_finalize_ok, expected):
    fake = FakeKakaoService()
    env = {"KAKAO_DELIVERY_STATE_ENABLED": "true", "KAKAO_DELIVERY_CUTOVER_APPROVED": "true"}
    with patch("services.kakao_delivery_staged.PostgresDeliveryAttempts") as store_class:
        store = store_class.return_value
        store.claim.return_value = uuid4()
        store.finish_sent_with_legacy.return_value = legacy_finalize_ok
        result = send_staged_morning_report(
            engine=object(), user_id=uuid4(), report_date=date(2026, 10, 12),
            kakao_service=fake, summary_text="report", report_web_url="https://example.com/report",
            env=env,
        )
        store.claim.assert_called_once()
        store.finish_sent_with_legacy.assert_called_once()
        store.finish.assert_not_called()
    assert result.outcome == expected
    assert result.needs_reconciliation is (not legacy_finalize_ok)
    assert fake.calls == [("report", "https://example.com/report")]


def test_adapter_atomic_finalizer_exception_is_uncertain_without_second_kakao_send():
    fake = FakeKakaoService()
    env = {"KAKAO_DELIVERY_STATE_ENABLED": "true", "KAKAO_DELIVERY_CUTOVER_APPROVED": "true"}
    with patch("services.kakao_delivery_staged.PostgresDeliveryAttempts") as store_class:
        store = store_class.return_value
        store.claim.return_value = uuid4()
        store.finish_sent_with_legacy.side_effect = RuntimeError("database connection dropped")
        result = send_staged_morning_report(
            engine=object(), user_id=uuid4(), report_date=date(2026, 10, 12),
            kakao_service=fake, summary_text="report", report_web_url="https://example.com/report",
            env=env,
        )
        store.claim.assert_called_once()
        store.finish_sent_with_legacy.assert_called_once()
        store.finish.assert_not_called()
    assert result.outcome == SendOutcome.UNCERTAIN
    assert result.needs_reconciliation
    assert fake.calls == [("report", "https://example.com/report")]


def test_unconfigured_kakao_service_does_not_claim_or_send():
    fake = FakeKakaoService()
    fake.is_configured = lambda: False
    with patch("services.kakao_delivery_transport_adapter.run_staged_delivery") as staged:
        result = send_staged_morning_report(
            engine=object(), user_id=uuid4(), report_date=date(2026, 10, 12),
            kakao_service=fake, summary_text="report", report_web_url="https://example.com",
            env={"KAKAO_DELIVERY_STATE_ENABLED": "true", "KAKAO_DELIVERY_CUTOVER_APPROVED": "true"},
        )
    assert result.outcome == SendOutcome.FAILED_BEFORE_SEND
    assert fake.calls == []
    staged.assert_not_called()


def test_disabled_rollout_never_inspects_kakao_credentials():
    class UnavailableService:
        def is_configured(self):
            pytest.fail("disabled rollout inspected Kakao credentials")

        def send_morning_report(self, *_):
            pytest.fail("disabled rollout sent Kakao message")

    with patch("services.kakao_delivery_transport_adapter.run_staged_delivery") as staged:
        result = send_staged_morning_report(
            engine=object(), user_id=uuid4(), report_date=date(2026, 10, 12),
            kakao_service=UnavailableService(), summary_text="test",
            report_web_url="https://example.com", env={},
        )
    assert result.outcome == SendOutcome.DISABLED
    staged.assert_not_called()


def test_configuration_check_exception_never_claims_or_sends():
    fake = FakeKakaoService()

    def unavailable():
        raise RuntimeError("credential lookup unavailable")

    fake.is_configured = unavailable
    with patch("services.kakao_delivery_transport_adapter.run_staged_delivery") as staged:
        with pytest.raises(RuntimeError, match="credential lookup unavailable"):
            send_staged_morning_report(
                engine=object(), user_id=uuid4(), report_date=date(2026, 10, 12),
                kakao_service=fake, summary_text="report",
                report_web_url="https://example.com",
                env={"KAKAO_DELIVERY_STATE_ENABLED": "true",
                     "KAKAO_DELIVERY_CUTOVER_APPROVED": "true"},
            )
    staged.assert_not_called()
    assert fake.calls == []


@pytest.mark.parametrize("missing_method", ["send_morning_report", "is_configured"])
def test_malformed_kakao_service_never_claims_or_sends(missing_method):
    fake = FakeKakaoService()
    setattr(fake, missing_method, None)
    with patch("services.kakao_delivery_transport_adapter.run_staged_delivery") as staged:
        with pytest.raises(TypeError, match="Kakao service must implement"):
            send_staged_morning_report(
                engine=object(), user_id=uuid4(), report_date=date(2026, 10, 12),
                kakao_service=fake, summary_text="report",
                report_web_url="https://example.com",
                env={"KAKAO_DELIVERY_STATE_ENABLED": "true",
                     "KAKAO_DELIVERY_CUTOVER_APPROVED": "true"},
            )
    staged.assert_not_called()
    assert fake.calls == []
