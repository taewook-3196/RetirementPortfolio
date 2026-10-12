"""Kakao delivery attempt state model (not wired into production sending yet).

A successful API response is not an exactly-once guarantee. In particular,
network failures after submission must remain ambiguous until reconciled.
"""
from dataclasses import dataclass
from enum import Enum


class DeliveryState(str, Enum):
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    UNCERTAIN = "uncertain"
    FAILED_BEFORE_SEND = "failed_before_send"


@dataclass(frozen=True)
class DeliveryDecision:
    state: DeliveryState
    automatic_retry_allowed: bool
    reason: str


def decide_retry(state: DeliveryState, *, lease_expired: bool = False) -> DeliveryDecision:
    """Fail closed on ambiguous outcomes; do not blindly resend Kakao messages."""
    if state in (DeliveryState.SENT, DeliveryState.UNCERTAIN):
        return DeliveryDecision(state, False, "already delivered or outcome uncertain")
    if state == DeliveryState.SENDING:
        return DeliveryDecision(
            state, False, "active attempt" if not lease_expired else "expired lease requires reconciliation"
        )
    if state in (DeliveryState.PENDING, DeliveryState.FAILED_BEFORE_SEND):
        return DeliveryDecision(state, True, "no send attempt started")
    raise ValueError(f"Unknown delivery state: {state!r}")
