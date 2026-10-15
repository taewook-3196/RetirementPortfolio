"""Pure review gate for a *future* operator-authorized Kakao recovery.

No database writes, credentials, or transport calls. Approval here is not a
claim permit: the current SQL claim function still rejects all prior attempts.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID


@dataclass(frozen=True)
class RecoveryReview:
    actor_id: UUID
    target_user_id: UUID
    attempt_id: UUID
    approved_at: datetime
    evidence_reference: str
    request_never_started: bool


@dataclass(frozen=True)
class RecoveryReviewDecision:
    eligible_for_future_recovery: bool
    reason: str


def assess_recovery_review(*, review: RecoveryReview, actor_is_admin: bool,
                           attempt_status: str, legacy_sent: bool) -> RecoveryReviewDecision:
    """Validate evidence and identity; never authorize an actual send."""
    deny = lambda reason: RecoveryReviewDecision(False, reason)
    if not isinstance(review, RecoveryReview):
        return deny("invalid review")
    if actor_is_admin is not True:
        return deny("admin authorization required")
    if not all(isinstance(value, UUID) for value in (
        review.actor_id, review.target_user_id, review.attempt_id
    )):
        return deny("invalid actor, target or attempt identifier")
    if review.actor_id != review.target_user_id:
        return deny("cross-user recovery is not authorized")
    if legacy_sent is not False:
        return deny("legacy delivery is recorded or unknown")
    if attempt_status != "failed_before_send":
        return deny("only confirmed pre-send failures may be reviewed")
    if review.request_never_started is not True:
        return deny("affirmative evidence of no Kakao request is required")
    if not isinstance(review.evidence_reference, str) or not review.evidence_reference.strip():
        return deny("audit evidence reference required")
    if len(review.evidence_reference) > 256:
        return deny("audit evidence reference too long")
    if not isinstance(review.approved_at, datetime) or review.approved_at.tzinfo is None:
        return deny("timezone-aware approval time required")
    if review.approved_at > datetime.now(timezone.utc):
        return deny("approval cannot be in the future")
    return RecoveryReviewDecision(True, "review inputs valid; recovery write path not implemented")
