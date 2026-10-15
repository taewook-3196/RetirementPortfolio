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
