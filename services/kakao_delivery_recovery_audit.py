"""Immutable, read-only audit record specification for future Kakao recovery.

This module neither persists an approval nor enables delivery. The production
claim function continues to deny all prior attempts.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from services.kakao_delivery_recovery_review import RecoveryReview, assess_recovery_review


@dataclass(frozen=True)
class RecoveryAuditRecord:
    actor_id: UUID
    target_user_id: UUID
    attempt_id: UUID
    reviewed_at: datetime
    evidence_reference: str
    decision: str
    reason: str


def build_recovery_audit_record(*, review: RecoveryReview, actor_is_admin: bool,
                                attempt_status: str, legacy_sent: bool) -> RecoveryAuditRecord:
    """Construct an audit event even for denied reviews; never include tokens."""
    if not isinstance(review, RecoveryReview):
        raise TypeError("review must be RecoveryReview")
    decision = assess_recovery_review(
        review=review, actor_is_admin=actor_is_admin,
        attempt_status=attempt_status, legacy_sent=legacy_sent,
    )
    if not all(isinstance(x, UUID) for x in (
        review.actor_id, review.target_user_id, review.attempt_id
    )):
        raise ValueError("invalid review identifiers")
    if not isinstance(review.evidence_reference, str):
        raise ValueError("invalid evidence reference")
    if not isinstance(review.approved_at, datetime) or review.approved_at.tzinfo is None:
        raise ValueError("timezone-aware review time required")
    return RecoveryAuditRecord(
        actor_id=review.actor_id, target_user_id=review.target_user_id,
        attempt_id=review.attempt_id, reviewed_at=review.approved_at.astimezone(timezone.utc),
        evidence_reference=review.evidence_reference[:256],
        decision="eligible_for_future_recovery" if decision.eligible_for_future_recovery else "denied",
        reason=decision.reason,
    )
