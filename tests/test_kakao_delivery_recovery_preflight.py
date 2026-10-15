from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from services.kakao_delivery_recovery_audit import RecoveryAuditRecord
from services.kakao_delivery_recovery_preflight import check_recovery_audit_preflight


class FakeResult:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def one_or_none(self):
        return self.row


class FakeConnection:
    def __init__(self, row):
        self.row = row
        self.executed = False

    def execute(self, statement, params):
        self.executed = True
        assert "SELECT" in str(statement)
        return FakeResult(self.row)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class FakeEngine:
    def __init__(self, row):
        self.conn = FakeConnection(row)

    def connect(self):
        return self.conn


def record(**changes):
    user = uuid4()
    values = dict(actor_id=user, target_user_id=user, attempt_id=uuid4(),
                  reviewed_at=datetime.now(timezone.utc), evidence_reference="ticket",
                  decision="eligible_for_future_recovery", reason="verified")
    values.update(changes)
    return RecoveryAuditRecord(**values)


def test_preflight_requires_trusted_admin_identity_before_db_read():
    item = record()
    engine = FakeEngine({"status": "failed_before_send", "kakao_sent_at": None})
    assert not check_recovery_audit_preflight(engine, record=item,
        authenticated_actor_id=uuid4(), resolve_admin=lambda _: True).allowed
    assert not engine.conn.executed
    assert not check_recovery_audit_preflight(engine, record=item,
        authenticated_actor_id=item.actor_id, resolve_admin=lambda _: False).allowed
    assert not engine.conn.executed


def test_preflight_rechecks_attempt_and_legacy_status():
    item = record()
    for row in (None, {"status": "uncertain", "kakao_sent_at": None},
                {"status": "failed_before_send", "kakao_sent_at": "sent"}):
        result = check_recovery_audit_preflight(FakeEngine(row), record=item,
            authenticated_actor_id=item.actor_id, resolve_admin=lambda _: True)
        assert not result.allowed
    result = check_recovery_audit_preflight(
        FakeEngine({"status": "failed_before_send", "kakao_sent_at": None}),
        record=item, authenticated_actor_id=item.actor_id, resolve_admin=lambda _: True)
    assert result.allowed
    assert "no persistence" in result.reason
