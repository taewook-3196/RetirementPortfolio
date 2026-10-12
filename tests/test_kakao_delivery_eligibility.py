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
@pytest.mark.parametrize("state", [None, "failed_before_send"])
def test_all_paths_can_request_atomic_claim_only_when_safe(origin, force, state):
    result = check_delivery_eligibility(origin=origin, legacy_sent=False, attempt_state=state, force=force)
    assert result.allowed


def test_unknown_origin_is_blocked():
    assert not check_delivery_eligibility(origin="manual", legacy_sent=False, attempt_state=None, force=True).allowed
