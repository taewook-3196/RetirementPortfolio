from datetime import datetime, timezone, timedelta
from uuid import uuid4

import pytest

from services.kakao_delivery_recovery_audit import RecoveryAuditRecord
from services.kakao_delivery_recovery_audit_writer import (
    RecoveryAuditWriteForbidden, append_recovery_audit,
)
from services.kakao_delivery_authenticated_recovery_write import append_for_authenticated_operator


def make_record(**changes):
    user = uuid4()
    fields = dict(actor_id=user, target_user_id=user, attempt_id=uuid4(),
                  reviewed_at=datetime.now(timezone.utc), evidence_reference="ticket-42",
                  decision="eligible_for_future_recovery", reason="verified no request")
    fields.update(changes)
    return RecoveryAuditRecord(**fields)


def test_invalid_actor_and_missing_evidence_never_open_connection():
    record = make_record()
    for bad_record, actor in (
        (record, uuid4()),
        (make_record(evidence_reference=""), record.actor_id),
    ):
        with pytest.raises(RecoveryAuditWriteForbidden):
            append_recovery_audit(None, record=bad_record, authenticated_admin_id=actor)


def test_verified_web_admin_is_used_for_write(monkeypatch):
    from web import app as web_app
    from services import kakao_delivery_authenticated_recovery_write as subject

    actor = uuid4()
    monkeypatch.setattr(web_app, "require_admin", lambda token: {"user_id": str(actor)})
    captured = {}

    def fake_append(engine, **kwargs):
        captured.update(kwargs)
        return 42

    monkeypatch.setattr(subject, "append_recovery_audit", fake_append)
    assert append_for_authenticated_operator(object(), authorization="Bearer test", record="record") == 42
    assert captured["authenticated_admin_id"] == actor


def test_rejected_web_admin_never_writes(monkeypatch):
    from fastapi import HTTPException
    from web import app as web_app
    from services import kakao_delivery_authenticated_recovery_write as subject

    monkeypatch.setattr(web_app, "require_admin", lambda _: (_ for _ in ()).throw(
        HTTPException(status_code=403, detail="forbidden")))
    monkeypatch.setattr(subject, "append_recovery_audit",
                        lambda *a, **k: pytest.fail("write must not occur"))
    with pytest.raises(HTTPException):
        append_for_authenticated_operator(object(), authorization="bad", record=None)


@pytest.mark.parametrize("reviewed_at", [
    datetime(2026, 10, 14),
    datetime.now(timezone.utc) + timedelta(days=1),
    None,
])
def test_invalid_review_timestamp_denied_before_db_access(reviewed_at):
    record = make_record(reviewed_at=reviewed_at)
    with pytest.raises(RecoveryAuditWriteForbidden):
        append_recovery_audit(None, record=record, authenticated_admin_id=record.actor_id)


def test_unverified_positive_recovery_decision_is_denied_before_db_access():
    record = make_record()
    with pytest.raises(RecoveryAuditWriteForbidden, match="verified server-side evidence"):
        append_recovery_audit(None, record=record, authenticated_admin_id=record.actor_id)
