import pytest

from services.kakao_delivery_reconciliation import ReconciliationAction, advise_reconciliation


@pytest.mark.parametrize("status", ["pending", "sending", "sent", "uncertain", "failed_before_send", "unknown"])
@pytest.mark.parametrize("expired", [False, True])
def test_no_status_authorizes_automatic_resend(status, expired):
    result = advise_reconciliation(attempt_status=status, lease_expired=expired)
    assert not result.automatic_resend_allowed


def test_uncertain_requires_external_verification():
    result = advise_reconciliation(attempt_status="uncertain")
    assert result.action == ReconciliationAction.VERIFY_EXTERNALLY


def test_expired_sending_requires_external_verification():
    result = advise_reconciliation(attempt_status="sending", lease_expired=True)
    assert result.action == ReconciliationAction.VERIFY_EXTERNALLY


def test_active_sending_does_not_prompt_retry():
    result = advise_reconciliation(attempt_status="sending", lease_expired=False)
    assert result.action == ReconciliationAction.NO_ACTION


def test_legacy_sent_marker_overrides_ambiguous_state():
    result = advise_reconciliation(attempt_status="uncertain", legacy_sent=True)
    assert result.action == ReconciliationAction.NO_ACTION


def test_pre_send_failure_requires_review_not_automatic_retry():
    result = advise_reconciliation(attempt_status="failed_before_send")
    assert result.action == ReconciliationAction.REVIEW_PRE_SEND_FAILURE
    assert not result.automatic_resend_allowed


@pytest.mark.parametrize("status", ["sending", "uncertain", "failed_before_send", "pending", "unknown"])
@pytest.mark.parametrize("expired", [False, True])
def test_legacy_sent_marker_never_authorizes_retry(status, expired):
    result = advise_reconciliation(attempt_status=status, lease_expired=expired, legacy_sent=True)
    assert result.action == ReconciliationAction.NO_ACTION
    assert not result.automatic_resend_allowed


def test_unrecognized_state_fails_closed_even_after_lease_expiry():
    result = advise_reconciliation(attempt_status="unexpected", lease_expired=True)
    assert result.action == ReconciliationAction.NO_ACTION
    assert not result.automatic_resend_allowed
