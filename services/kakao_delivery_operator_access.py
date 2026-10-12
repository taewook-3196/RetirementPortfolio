"""Authorization boundary for staged operator delivery inspection.

Caller must independently establish the current authenticated identity and role.
No public route or UI imports this module.
"""

from uuid import UUID

from services.kakao_delivery_inspection import inspect_delivery_attempts


class DeliveryInspectionForbidden(PermissionError):
    pass


def inspect_for_operator(engine, *, actor_id: UUID, actor_is_admin: bool,
                         target_user_id: UUID, limit: int = 30):
    """Require an explicitly authorized admin before any database read."""
    if not isinstance(actor_id, UUID) or not isinstance(target_user_id, UUID):
        raise DeliveryInspectionForbidden("valid authenticated actor and target required")
    if actor_is_admin is not True:
        raise DeliveryInspectionForbidden("admin authorization required")
    return inspect_delivery_attempts(engine, user_id=target_user_id, limit=limit)
