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
    result = send_with_delivery_claim(claim=lambda: 1, transport=lambda: events.append("send") or (True, "mock"), finish=lambda status: events.append(status) or True, env=ON)
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
    result = send_with_delivery_claim(claim=lambda: 1, transport=lambda: (True, "mock"), finish=lambda _: False, env=ON)
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


@pytest.mark.parametrize("response", [None, (), (True,), (True, "ok", "extra"), (1, "ok"), 0, "ok", {}, []])
def test_missing_or_malformed_success_is_uncertain(response):
    states = []
    result = send_with_delivery_claim(
        claim=lambda: 1,
        transport=lambda: response,
        finish=lambda status: states.append(status) or True,
        env=ON,
    )
    assert result.outcome == SendOutcome.UNCERTAIN
    assert result.needs_reconciliation
    assert states == ["uncertain"]


@pytest.mark.parametrize("origin", ["scheduled", "manual", "cli", "cached"])
def test_every_entry_origin_requires_claim_before_transport(origin):
    events = []
    def claim():
        events.append((origin, "claim"))
        return 1
    def transport():
        events.append((origin, "transport"))
        return (True, "mock")
    def finish(status):
        events.append((origin, status))
        return True
    result = send_with_delivery_claim(claim=claim, transport=transport, finish=finish, env=ON)
    assert result.outcome == SendOutcome.SENT
    assert events == [(origin, "claim"), (origin, "transport"), (origin, "sent")]


@pytest.mark.parametrize("origin", ["scheduled", "manual", "cli"])
def test_every_entry_origin_denied_claim_never_transports(origin):
    events = []
    result = send_with_delivery_claim(
        claim=lambda: events.append((origin, "claim")) or None,
        transport=lambda: pytest.fail(f"{origin} bypassed claim"),
        finish=lambda _: pytest.fail("denied claim finalized"),
        env=ON,
    )
    assert result.outcome == SendOutcome.NOT_CLAIMED
    assert events == [(origin, "claim")]


@pytest.mark.parametrize("denial", [None, False])
@pytest.mark.parametrize("origin", ["scheduled", "manual", "cli"])
def test_false_or_none_claim_denial_never_reaches_transport(origin, denial):
    events = []
    result = send_with_delivery_claim(
        claim=lambda: events.append((origin, "claim")) or denial,
        transport=lambda: pytest.fail(f"{origin} attempted send without claim"),
        finish=lambda _: pytest.fail("denied claim finalized"),
        env=ON,
    )
    assert result.outcome == SendOutcome.NOT_CLAIMED
    assert events == [(origin, "claim")]


@pytest.mark.parametrize("origin", ["scheduled", "manual", "cli"])
def test_shared_mock_transport_is_called_once_after_claim_across_origins(origin):
    from services.kakao_delivery_orchestrator import SendOutcome, send_with_delivery_claim

    events = []
    gate = {"KAKAO_DELIVERY_STATE_ENABLED": "true", "KAKAO_DELIVERY_CUTOVER_APPROVED": "true"}
    result = send_with_delivery_claim(
        claim=lambda: events.append((origin, "claim")) or 123,
        transport=lambda: events.append((origin, "transport")) or (True, "ok"),
        finish=lambda status: events.append((origin, status)) or True,
        env=gate,
    )
    assert result.outcome == SendOutcome.SENT
    assert events == [(origin, "claim"), (origin, "transport"), (origin, "sent")]


@pytest.mark.parametrize("origin", ["scheduled", "manual", "cli"])
def test_shared_mock_transport_never_runs_when_claim_is_denied(origin):
    from services.kakao_delivery_orchestrator import SendOutcome, send_with_delivery_claim

    events = []
    gate = {"KAKAO_DELIVERY_STATE_ENABLED": "true", "KAKAO_DELIVERY_CUTOVER_APPROVED": "true"}
    result = send_with_delivery_claim(
        claim=lambda: events.append((origin, "denied")) or None,
        transport=lambda: events.append((origin, "transport")) or (True, "ok"),
        finish=lambda status: events.append((origin, status)) or True,
        env=gate,
    )
    assert result.outcome == SendOutcome.NOT_CLAIMED
    assert events == [(origin, "denied")]


@pytest.mark.parametrize("origin", ["scheduled", "manual", "cli"])
@pytest.mark.parametrize("response", [(False, "timeout"), None, (True,), "unexpected"])
def test_ambiguous_mock_transport_requires_review_for_every_origin(origin, response):
    from services.kakao_delivery_orchestrator import SendOutcome, send_with_delivery_claim

    events = []
    gate = {"KAKAO_DELIVERY_STATE_ENABLED": "true", "KAKAO_DELIVERY_CUTOVER_APPROVED": "true"}
    result = send_with_delivery_claim(
        claim=lambda: events.append((origin, "claim")) or 123,
        transport=lambda: events.append((origin, "transport")) or response,
        finish=lambda status: events.append((origin, status)) or True,
        env=gate,
    )
    assert result.outcome == SendOutcome.UNCERTAIN
    assert result.needs_reconciliation
    assert events == [(origin, "claim"), (origin, "transport"), (origin, "uncertain")]


@pytest.mark.parametrize("origin", ["scheduled", "manual", "cli"])
@pytest.mark.parametrize("finalized", [False, None])
def test_successful_transport_with_failed_marker_finalization_requires_review(origin, finalized):
    from services.kakao_delivery_orchestrator import SendOutcome, send_with_delivery_claim

    events = []
    gate = {"KAKAO_DELIVERY_STATE_ENABLED": "true", "KAKAO_DELIVERY_CUTOVER_APPROVED": "true"}
    result = send_with_delivery_claim(
        claim=lambda: events.append((origin, "claim")) or 123,
        transport=lambda: events.append((origin, "transport")) or (True, "ok"),
        finish=lambda status: events.append((origin, status)) or finalized,
        env=gate,
    )
    assert result.outcome == SendOutcome.UNCERTAIN
    assert result.needs_reconciliation
    assert events == [(origin, "claim"), (origin, "transport"), (origin, "sent")]


@pytest.mark.parametrize("origin", ["scheduled", "manual", "cli"])
def test_finalization_exception_after_success_never_reinvokes_transport(origin):
    from services.kakao_delivery_orchestrator import SendOutcome, send_with_delivery_claim

    events = []
    gate = {"KAKAO_DELIVERY_STATE_ENABLED": "true", "KAKAO_DELIVERY_CUTOVER_APPROVED": "true"}

    def finish(status):
        events.append((origin, status))
        raise RuntimeError("database unavailable after Kakao acceptance")

    result = send_with_delivery_claim(
        claim=lambda: events.append((origin, "claim")) or 123,
        transport=lambda: events.append((origin, "transport")) or (True, "ok"),
        finish=finish,
        env=gate,
    )
    assert result.outcome == SendOutcome.UNCERTAIN
    assert result.needs_reconciliation
    assert events == [(origin, "claim"), (origin, "transport"), (origin, "sent")]


@pytest.mark.parametrize("origin", ["scheduled", "manual", "cli"])
def test_claim_database_exception_prevents_any_transport_call(origin):
    from services.kakao_delivery_orchestrator import send_with_delivery_claim

    events = []
    gate = {"KAKAO_DELIVERY_STATE_ENABLED": "true", "KAKAO_DELIVERY_CUTOVER_APPROVED": "true"}

    def claim():
        events.append((origin, "claim"))
        raise RuntimeError("database unavailable before Kakao send")

    with pytest.raises(RuntimeError, match="database unavailable before Kakao send"):
        send_with_delivery_claim(
            claim=claim,
            transport=lambda: events.append((origin, "transport")) or (True, "ok"),
            finish=lambda status: events.append((origin, status)) or True,
            env=gate,
        )
    assert events == [(origin, "claim")]


@pytest.mark.parametrize("response", [(True, "ok"), (False, "timeout"), None])
def test_two_invocations_with_shared_atomic_claim_never_double_send(response):
    """A deterministic shared-claim contract, not a substitute for PostgreSQL concurrency tests."""
    claimed = False
    calls = []

    def claim():
        nonlocal claimed
        if claimed:
            return None
        claimed = True
        return 101

    def transport():
        calls.append("kakao")
        return response

    first = send_with_delivery_claim(claim=claim, transport=transport, finish=lambda _: True, env=ON)
    second = send_with_delivery_claim(claim=claim, transport=transport, finish=lambda _: True, env=ON)
    assert first.outcome in (SendOutcome.SENT, SendOutcome.UNCERTAIN)
    assert second.outcome == SendOutcome.NOT_CLAIMED
    assert calls == ["kakao"]


def test_commit_error_after_transport_never_causes_second_send():
    claimed = False
    calls = []

    def claim():
        nonlocal claimed
        if claimed:
            return None
        claimed = True
        return 101

    def transport():
        calls.append("kakao")
        return (True, "accepted")

    def finish(_):
        raise ConnectionError("commit acknowledgement lost")

    first = send_with_delivery_claim(claim=claim, transport=transport, finish=finish, env=ON)
    second = send_with_delivery_claim(claim=claim, transport=transport, finish=finish, env=ON)
    assert first.outcome == SendOutcome.UNCERTAIN
    assert first.needs_reconciliation
    assert second.outcome == SendOutcome.NOT_CLAIMED
    assert calls == ["kakao"]


@pytest.mark.parametrize("bad_claim", [0, "", (), [], {}])
def test_non_authoritative_claim_values_must_not_trigger_transport(bad_claim):
    """Only a real persisted claim identifier may authorize an external send."""
    result = send_with_delivery_claim(
        claim=lambda: bad_claim,
        transport=lambda: pytest.fail("transport called without a valid claim"),
        finish=lambda _: pytest.fail("finalized without a valid claim"),
        env=ON,
    )
    assert result.outcome == SendOutcome.NOT_CLAIMED
