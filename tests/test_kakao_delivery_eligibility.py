import pytest

from services.kakao_delivery_eligibility import DeliveryOrigin, check_delivery_eligibility


@pytest.mark.parametrize("origin", list(DeliveryOrigin))
@pytest.mark.parametrize("force", [False, True])
def test_all_paths_block_already_sent_legacy_report(origin, force):
    result = check_delivery_eligibility(origin=origin, legacy_sent=True, attempt_state=None, force=force)
    assert not result.allowed


@pytest.mark.parametrize("origin", list(DeliveryOrigin))
@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("state", ["pending", "sending", "sent", "uncertain", "unknown"])
def test_all_paths_block_existing_attempt_even_when_forced(origin, force, state):
    result = check_delivery_eligibility(origin=origin, legacy_sent=False, attempt_state=state, force=force)
    assert not result.allowed


@pytest.mark.parametrize("origin", list(DeliveryOrigin))
@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("state", [None])
def test_all_paths_can_request_atomic_claim_only_when_safe(origin, force, state):
    result = check_delivery_eligibility(origin=origin, legacy_sent=False, attempt_state=state, force=force)
    assert result.allowed


def test_unknown_origin_is_blocked():
    assert not check_delivery_eligibility(origin="manual", legacy_sent=False, attempt_state=None, force=True).allowed


@pytest.mark.parametrize("origin", list(DeliveryOrigin))
@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("state", ["sending", "uncertain", "sent"])
def test_force_never_bypasses_ambiguous_or_confirmed_send_across_entrypoints(origin, force, state):
    eligible = check_delivery_eligibility(
        origin=origin, legacy_sent=False, attempt_state=state, force=force,
    )
    assert eligible.allowed is False
    assert eligible.reason == "existing or ambiguous delivery attempt"


@pytest.mark.parametrize("origin", list(DeliveryOrigin))
def test_pre_send_failure_requires_operator_review_before_new_claim(origin):
    result = check_delivery_eligibility(
        origin=origin, legacy_sent=False, attempt_state="failed_before_send", force=True,
    )
    assert result.allowed is False
    assert result.reason == "pre-send failure requires reviewed recovery"


@pytest.mark.parametrize("field, invalid", [
    ("legacy_sent", None), ("legacy_sent", "false"), ("legacy_sent", 0),
    ("force", None), ("force", "true"), ("force", 1),
    ("attempt_state", False), ("attempt_state", 0), ("attempt_state", []),
])
@pytest.mark.parametrize("origin", list(DeliveryOrigin))
def test_unknown_delivery_state_fails_closed_for_every_origin(origin, field, invalid):
    args = dict(origin=origin, legacy_sent=False, attempt_state=None, force=False)
    args[field] = invalid
    result = check_delivery_eligibility(**args)
    assert result.allowed is False
    assert result.reason == "invalid or unknown delivery state"


@pytest.mark.parametrize("force", [False, True])
def test_cached_origin_never_bypasses_prior_attempt(force):
    result = check_delivery_eligibility(
        origin=DeliveryOrigin.CACHED, legacy_sent=False,
        attempt_state="uncertain", force=force,
    )
    assert result.allowed is False


@pytest.mark.parametrize("origin", list(DeliveryOrigin))
@pytest.mark.parametrize("force", [False, True])
def test_policy_eligibility_still_requires_committed_database_claim(monkeypatch, origin, force):
    """All four origins must fail closed even after optimistic policy approval."""
    from datetime import date
    from uuid import uuid4
    from services.kakao_delivery_staged import run_staged_delivery
    from services.kakao_delivery_orchestrator import SendOutcome

    decision = check_delivery_eligibility(
        origin=origin, legacy_sent=False, attempt_state=None, force=force,
    )
    assert decision.allowed

    class RejectingStore:
        def __init__(self, engine):
            pass

        def claim(self, attempt):
            return None

        def finish(self, attempt, status):
            pytest.fail("denied claim must not finish")

        def finish_sent_with_legacy(self, attempt):
            pytest.fail("denied claim must not mark legacy sent")

    monkeypatch.setattr(
        "services.kakao_delivery_staged.PostgresDeliveryAttempts", RejectingStore
    )
    result = run_staged_delivery(
        engine=None, user_id=uuid4(), report_date=date(2026, 10, 14),
        transport=lambda: pytest.fail(f"{origin.value} bypassed DB claim"),
        env={"KAKAO_DELIVERY_STATE_ENABLED": "true", "KAKAO_DELIVERY_CUTOVER_APPROVED": "true"},
    )
    assert result.outcome == SendOutcome.NOT_CLAIMED
