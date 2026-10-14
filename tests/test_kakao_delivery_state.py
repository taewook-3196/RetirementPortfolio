from services.kakao_delivery_state import DeliveryState, decide_retry


def test_pending_can_retry_before_any_send_attempt():
    assert decide_retry(DeliveryState.PENDING).automatic_retry_allowed is True


def test_pre_send_failure_requires_operator_review():
    decision = decide_retry(DeliveryState.FAILED_BEFORE_SEND)
    assert decision.automatic_retry_allowed is False
    assert "reviewed recovery" in decision.reason


def test_sent_and_uncertain_never_auto_retry():
    for state in (DeliveryState.SENT, DeliveryState.UNCERTAIN):
        assert decide_retry(state).automatic_retry_allowed is False


def test_expired_sending_lease_requires_reconciliation():
    assert decide_retry(DeliveryState.SENDING).automatic_retry_allowed is False
    decision = decide_retry(DeliveryState.SENDING, lease_expired=True)
    assert decision.automatic_retry_allowed is False
    assert "reconciliation" in decision.reason
