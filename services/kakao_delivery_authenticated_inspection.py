"""Server-authenticated adapter for staged delivery inspection.

No route calls this adapter yet. Authentication is delegated to the existing
Supabase-backed web.app.require_admin; client-supplied identity is ignored.
"""

from uuid import UUID

from services.kakao_delivery_operator_access import inspect_for_operator


def inspect_for_authenticated_operator(engine, *, authorization: str | None,
                                       limit: int = 30):
    from web.app import require_admin

    user = require_admin(authorization)
    actor_id = UUID(str(user["user_id"]))
    return inspect_for_operator(
        engine, actor_id=actor_id, actor_is_admin=True,
        target_user_id=actor_id, limit=limit,
    )
