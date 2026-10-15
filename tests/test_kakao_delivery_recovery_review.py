from datetime import datetime, timedelta, timezone
from uuid import uuid4

from services.kakao_delivery_recovery_review import RecoveryReview, assess_recovery_review


def make_review(**overrides):
    user = uuid4()
    values = dict(
        actor_id=user, target_user_id=user, attempt_id=uuid4(),
        approved_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        evidence_reference="audit-ticket-123", request_never_started=True,
    )
    values.update(overrides)
    return RecoveryReview(**values)


def decide(review, **overrides):
    options = dict(actor_is_admin=True, attempt_status="failed_before_send", legacy_sent=False)
    options.update(overrides)
    return assess_recovery_review(review=review, **options)


def test_valid_review_does_not_grant_send_or_change_database():
    decision = decide(make_review())
    assert decision.eligible_for_future_recovery
    assert "not implemented" in decision.reason


def test_admin_and_same_user_required():
    review = make_review()
    assert not decide(review, actor_is_admin=False).eligible_for_future_recovery
    assert not decide(make_review(target_user_id=uuid4())).eligible_for_future_recovery


def test_only_proven_pre_send_failure_without_legacy_marker():
    review = make_review()
    for status in ("sending", "uncertain", "sent", "pending", "unknown"):
        assert not decide(review, attempt_status=status).eligible_for_future_recovery
    assert not decide(review, legacy_sent=True).eligible_for_future_recovery
    assert not decide(review, legacy_sent=None).eligible_for_future_recovery
    assert not decide(make_review(request_never_started=False)).eligible_for_future_recovery


def test_auditable_evidence_and_time_required():
    assert not decide(make_review(evidence_reference=" ")).eligible_for_future_recovery
    assert not decide(make_review(evidence_reference="x" * 257)).eligible_for_future_recovery
    assert not decide(make_review(approved_at=datetime.now())).eligible_for_future_recovery
    assert not decide(make_review(approved_at=datetime.now(timezone.utc) + timedelta(days=1))).eligible_for_future_recovery


def test_audit_reference_rejects_control_characters():
    for reference in ("ticket\\nspoofed", "ticket\\rspoofed", "ticket\\tspoofed", "ticket\\x00spoofed", "ticket\\x7fspoofed"):
        decision = decide(make_review(evidence_reference=reference))
        assert not decision.eligible_for_future_recovery
        assert "control characters" in decision.reason


def test_audit_reference_allows_regular_ticket_identifiers():
    assert decide(make_review(evidence_reference="OPS-2026/10/15 #42")).eligible_for_future_recovery
