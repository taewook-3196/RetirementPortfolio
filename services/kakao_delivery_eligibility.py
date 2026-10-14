"""Shared conservative send eligibility policy for scheduled and manual paths.

Staged only: not imported by production sender or CLI yet. Explicit manual
force may regenerate a report but cannot override a prior or ambiguous send.
"""

from dataclasses import dataclass
from enum import Enum


class DeliveryOrigin(str, Enum):
    SCHEDULED = "scheduled"
    MANUAL = "manual"
    CLI = "cli"


@dataclass(frozen=True)
class Eligibility:
    allowed: bool
    reason: str


def check_delivery_eligibility(*, origin: DeliveryOrigin, legacy_sent: bool,
                               attempt_state: str | None, force: bool = False) -> Eligibility:
    """Same duplicate protection for every origin, including forced requests.

    Unknown attempt states are blocked. A new claim is still required even
    after this check; this policy is not a replacement for the DB constraint.
    """
    if not isinstance(origin, DeliveryOrigin):
        return Eligibility(False, "unknown delivery origin")
    if legacy_sent:
        return Eligibility(False, "legacy delivery already recorded")
    if attempt_state is None:
        return Eligibility(True, "eligible for atomic claim")
    # The active-attempt partial unique index excludes failed_before_send,
    # but only an operator-confirmed pre-transport failure is safe to retry.
    # This policy intentionally fails closed until that recovery is explicit.
    if attempt_state == "failed_before_send":
        return Eligibility(False, "pre-send failure requires reviewed recovery")
    return Eligibility(False, "existing or ambiguous delivery attempt")
