import pytest

from services.kakao_delivery_orchestrator import SendOutcome, send_with_delivery_claim


ON = {"KAKAO_DELIVERY_STATE_ENABLED": "true", "KAKAO_DELIVERY_CUTOVER_APPROVED": "true"}


def test_disabled_gate_never_claims_or_sends():
    def forbidden():
        raise AssertionError("must not be called")
    result = send_with_delivery_claim(claim=forbidden, transport=forbidden, finish=forbidden, env={})
    assert result.outcome == SendOutcome.DISABLED


def test_denied_claim_never_sends():
    result = send_with_delivery_claim(claim=lambda: None, transport=lambda: pytest.fail("sent"), finish=lambda _: None, env=ON)
    assert result.outcome == SendOutcome.NOT_CLAIMED


def test_claim_db_failure_never_sends():
    def fail():
        raise RuntimeError("database unavailable")
    with pytest.raises(RuntimeError):
        send_with_delivery_claim(claim=fail, transport=lambda: pytest.fail("sent"), finish=lambda _: None, env=ON)


def test_successful_claim_and_completion():
    events = []
    result = send_with_delivery_claim(claim=lambda: 1, transport=lambda: events.append("send"), finish=lambda status: events.append(status) or True, env=ON)
    assert result.outcome == SendOutcome.SENT
    assert events == ["send", "sent"]


def test_transport_timeout_is_uncertain_not_retryable():
    events = []
    def timeout():
        events.append("send")
        raise TimeoutError("response lost")
    result = send_with_delivery_claim(claim=lambda: 1, transport=timeout, finish=lambda status: events.append(status) or True, env=ON)
    assert result.outcome == SendOutcome.UNCERTAIN
    assert result.needs_reconciliation
    assert events == ["send", "uncertain"]


def test_finish_db_failure_after_send_is_uncertain():
    events = []
    def finish(_):
        raise ConnectionError("db commit failed")
    result = send_with_delivery_claim(claim=lambda: 1, transport=lambda: events.append("send"), finish=finish, env=ON)
    assert result.outcome == SendOutcome.UNCERTAIN
    assert events == ["send"]


def test_finish_rejected_after_send_is_uncertain():
    result = send_with_delivery_claim(claim=lambda: 1, transport=lambda: None, finish=lambda _: False, env=ON)
    assert result.outcome == SendOutcome.UNCERTAIN


def test_kakao_success_tuple_is_sent():
    result = send_with_delivery_claim(claim=lambda: 1, transport=lambda: (True, "ok"), finish=lambda _: True, env=ON)
    assert result.outcome == SendOutcome.SENT


@pytest.mark.parametrize("response", [(False, "timeout"), (False, "HTTP 403"), False])
def test_kakao_failure_response_must_not_be_recorded_as_sent(response):
    states = []
    result = send_with_delivery_claim(claim=lambda: 1, transport=lambda: response, finish=lambda status: states.append(status) or True, env=ON)
    assert result.outcome == SendOutcome.UNCERTAIN
    assert result.needs_reconciliation
    assert states == ["uncertain"]
