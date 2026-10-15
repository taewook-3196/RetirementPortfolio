"""Read-only reconciliation guidance for staged Kakao delivery attempts.

A Kakao timeout cannot be safely retried without external confirmation.
This module never changes database state or sends a message.
"""

from dataclasses import dataclass
from enum import Enum


class ReconciliationAction(str, Enum):
    NO_ACTION = "no_action"
    VERIFY_EXTERNALLY = "verify_externally"
    REVIEW_PRE_SEND_FAILURE = "review_pre_send_failure"


@dataclass(frozen=True)
class ReconciliationAdvice:
    action: ReconciliationAction
    automatic_resend_allowed: bool
    reason: str


def advise_reconciliation(*, attempt_status: str, lease_expired: bool = False,
                          legacy_sent: bool = False) -> ReconciliationAdvice:
    if legacy_sent is True or attempt_status == "sent":
        return ReconciliationAdvice(ReconciliationAction.NO_ACTION, False, "delivery recorded")
    if legacy_sent is not False:
        return ReconciliationAdvice(ReconciliationAction.VERIFY_EXTERNALLY, False, "legacy delivery marker unknown")
    if attempt_status == "uncertain":
        return ReconciliationAdvice(ReconciliationAction.VERIFY_EXTERNALLY, False, "transport outcome ambiguous")
    if attempt_status == "sending":
        reason = "expired claim requires external verification" if lease_expired else "active send attempt"
        return ReconciliationAdvice(ReconciliationAction.VERIFY_EXTERNALLY if lease_expired else ReconciliationAction.NO_ACTION, False, reason)
    if attempt_status == "failed_before_send":
        return ReconciliationAdvice(ReconciliationAction.REVIEW_PRE_SEND_FAILURE, False, "verify no network request began before new claim")
    return ReconciliationAdvice(ReconciliationAction.NO_ACTION, False, "unrecognized or pending state: no automatic resend")
