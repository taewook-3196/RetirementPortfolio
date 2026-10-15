"""Authenticated server-only entry point for staged audit writes.

No public endpoint invokes this. No delivery claim is reopened.
"""
from uuid import UUID

from services.kakao_delivery_recovery_audit_writer import append_recovery_audit


def append_for_authenticated_operator(engine, *, authorization: str | None, record):
    from web.app import require_admin

    admin = require_admin(authorization)
    actor_id = UUID(str(admin["user_id"]))
    return append_recovery_audit(
        engine, record=record, authenticated_admin_id=actor_id,
    )
