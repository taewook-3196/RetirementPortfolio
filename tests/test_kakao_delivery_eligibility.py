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
