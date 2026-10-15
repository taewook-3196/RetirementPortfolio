"""Read-only legacy/new Kakao delivery consistency assessment.

Used for staged cutover audits only. No database mutations or sends.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class MarkerAssessment:
    consistent: bool
    requires_review: bool
    reason: str


def assess_delivery_markers(*, legacy_sent: bool, new_status: str | None) -> MarkerAssessment:
    if new_status is None:
        return MarkerAssessment(True, False, "legacy-only report before cutover")
    if new_status == "sent":
        if legacy_sent:
            return MarkerAssessment(True, False, "both markers record sent")
        return MarkerAssessment(False, True, "new sent marker missing legacy confirmation")
    if legacy_sent:
        return MarkerAssessment(False, True, "legacy sent marker conflicts with unfinished new attempt")
    if new_status in {"pending", "sending", "uncertain", "failed_before_send"}:
        return MarkerAssessment(True, new_status in {"sending", "uncertain"}, "no confirmed delivery")
    return MarkerAssessment(False, True, "unknown new delivery state")
