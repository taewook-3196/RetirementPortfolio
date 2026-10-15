from uuid import uuid4

import pytest

from services.kakao_delivery_operator_access import (
    DeliveryInspectionForbidden,
    inspect_for_operator,
)


class NoDatabaseAccess:
    def connect(self):
        raise AssertionError("Unauthorized request accessed the database")


@pytest.mark.parametrize("admin", [False, None, 0, "true", "admin"])
def test_non_admin_denied_before_db_access(admin):
    with pytest.raises(DeliveryInspectionForbidden):
        inspect_for_operator(NoDatabaseAccess(), actor_id=uuid4(), actor_is_admin=admin,
                             target_user_id=uuid4())


@pytest.mark.parametrize("actor,target", [("", None), (None, None), ("not-a-uuid", uuid4()), (uuid4(), "not-a-uuid")])
def test_invalid_identity_denied_before_db_access(actor, target):
    with pytest.raises(DeliveryInspectionForbidden):
        inspect_for_operator(NoDatabaseAccess(), actor_id=actor, actor_is_admin=True,
                             target_user_id=target)


def test_inspection_query_preserves_missing_report_as_unknown():
    from datetime import date
    from services.kakao_delivery_inspection import inspect_delivery_attempts

    actor = uuid4()

    class FakeResult:
        def mappings(self):
            return self

        def all(self):
            return [dict(user_id=actor, report_date=date(2026, 10, 15),
                         status="failed_before_send", legacy_sent=None)]

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, statement, params):
            assert "CASE WHEN r.user_id IS NULL THEN NULL" in str(statement)
            assert params["user_id"] == actor
            return FakeResult()

    class FakeEngine:
        def connect(self):
            return FakeConnection()

    result = inspect_delivery_attempts(FakeEngine(), user_id=actor)
    assert len(result) == 1
    assert result[0].legacy_sent is None
    assert result[0].requires_review is True
