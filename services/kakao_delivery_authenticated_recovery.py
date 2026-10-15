"""Authenticated, read-only Kakao recovery audit preflight adapter.

Uses the existing Supabase-backed web.app.require_admin and derives identity
from its verified session. Does not write audit rows or send messages.
"""
from uuid import UUID

from services.kakao_delivery_recovery_preflight import check_recovery_audit_preflight


def preflight_for_authenticated_operator(engine, *, authorization: str | None, record):
    from web.app import require_admin

    user = require_admin(authorization)
    actor_id = UUID(str(user["user_id"]))
    return check_recovery_audit_preflight(
        engine,
        record=record,
        authenticated_actor_id=actor_id,
        resolve_admin=lambda candidate: candidate == actor_id,
    )
