from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from services.kakao_delivery_recovery_audit import build_recovery_audit_record
from services.kakao_delivery_recovery_review import RecoveryReview


def review(**changes):
    user = uuid4()
    values = dict(actor_id=user, target_user_id=user, attempt_id=uuid4(),
                  approved_at=datetime.now(timezone.utc) - timedelta(minutes=1),
                  evidence_reference="incident-42", request_never_started=True)
    values.update(changes)
    return RecoveryReview(**values)


def test_eligible_review_produces_non_authorizing_audit_event():
    event = build_recovery_audit_record(
        review=review(), actor_is_admin=True,
        attempt_status="failed_before_send", legacy_sent=False,
    )
    assert event.decision == "eligible_for_future_recovery"
    assert event.evidence_reference == "incident-42"
    assert event.reviewed_at.tzinfo == timezone.utc
    assert not hasattr(event, "send_allowed")


def test_denied_review_still_produces_audit_event():
    event = build_recovery_audit_record(
        review=review(), actor_is_admin=False,
        attempt_status="failed_before_send", legacy_sent=False,
    )
    assert event.decision == "denied"
    assert "admin" in event.reason


def test_audit_event_rejects_missing_identity_or_timezone():
    with pytest.raises(ValueError):
        build_recovery_audit_record(
            review=review(actor_id="not-a-uuid"), actor_is_admin=True,
            attempt_status="failed_before_send", legacy_sent=False,
        )
    with pytest.raises(ValueError):
        build_recovery_audit_record(
            review=review(approved_at=datetime.now()), actor_is_admin=True,
            attempt_status="failed_before_send", legacy_sent=False,
        )
