"""Isolated, opt-in Kakao delivery orchestration; not wired into scheduler.

The caller must provide a transactionally durable claim and a transport.
Never call the transport when claim is denied or cannot be persisted.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Callable

from services.kakao_delivery_feature_gate import evaluate_delivery_feature_gate


class SendOutcome(str, Enum):
    DISABLED = "disabled"
    NOT_CLAIMED = "not_claimed"
    SENT = "sent"
    UNCERTAIN = "uncertain"
    FAILED_BEFORE_SEND = "failed_before_send"


@dataclass(frozen=True)
class SendResult:
    outcome: SendOutcome
    needs_reconciliation: bool = False


def send_with_delivery_claim(
    *,
    claim: Callable[[], object],
    transport: Callable[[], object],
    finish: Callable[[str], object],
    env=None,
) -> SendResult:
    """Run a single attempt, conservatively classifying transport exceptions.

    Claim must be committed before it returns. A transport exception is always
    uncertain because the remote API may have accepted the message. A finish
    failure after a successful send must not cause another send attempt.
    """
    if not evaluate_delivery_feature_gate(env).enabled:
        return SendResult(SendOutcome.DISABLED)
    claim_id = claim()  # propagate DB errors: fail closed, do not call transport
    if claim_id is None:
        return SendResult(SendOutcome.NOT_CLAIMED)
    try:
        response = transport()
        # The existing KakaoService returns (ok, message), not an exception.
        # A negative result is not proof that the API never accepted a send:
        # timeouts and remote failures can be ambiguous. Fail closed.
        if response is not True and not (
            isinstance(response, tuple)
            and len(response) == 2
            and response[0] is True
        ):
            try:
                finish("uncertain")
            except Exception:
                pass
            return SendResult(SendOutcome.UNCERTAIN, needs_reconciliation=True)
    except Exception:
        try:
            finish("uncertain")
        except Exception:
            pass  # preserve uncertainty; never retry automatically
        return SendResult(SendOutcome.UNCERTAIN, needs_reconciliation=True)
    try:
        finalized = finish("sent")
    except Exception:
        return SendResult(SendOutcome.UNCERTAIN, needs_reconciliation=True)
    if finalized is not True:
        return SendResult(SendOutcome.UNCERTAIN, needs_reconciliation=True)
    return SendResult(SendOutcome.SENT)
