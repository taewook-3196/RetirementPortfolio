import pytest

from services.kakao_delivery_marker_audit import assess_delivery_markers


@pytest.mark.parametrize("legacy,status", [(False, None), (True, None), (True, "sent"), (False, "pending"), (False, "failed_before_send")])
def test_consistent_marker_states(legacy, status):
    assert assess_delivery_markers(legacy_sent=legacy, new_status=status).consistent


@pytest.mark.parametrize("legacy,status", [(False, "sent"), (True, "uncertain"), (True, "sending"), (True, "failed_before_send"), (True, "pending"), (False, "unknown")])
def test_inconsistent_markers_require_manual_review(legacy, status):
    result = assess_delivery_markers(legacy_sent=legacy, new_status=status)
    assert not result.consistent
    assert result.requires_review


def test_uncertain_state_always_requires_review():
    result = assess_delivery_markers(legacy_sent=False, new_status="uncertain")
    assert result.consistent
    assert result.requires_review
