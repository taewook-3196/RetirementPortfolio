"""Server-side read-only preflight for recovery audit persistence.

No INSERT or send. Caller supplies an authenticated actor resolved by the
trusted backend, not a client-controlled actor_is_admin flag.
"""
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text

from services.kakao_delivery_recovery_audit import RecoveryAuditRecord


@dataclass(frozen=True)
class RecoveryAuditPreflight:
    allowed: bool
    reason: str


def check_recovery_audit_preflight(engine, *, record: RecoveryAuditRecord,
                                   authenticated_actor_id: UUID,
                                   resolve_admin):
    """Recheck identity, admin role, attempt ownership and legacy marker.

    resolve_admin must be a trusted server-side authorization lookup accepting
    a UUID and returning exactly True for an authorized admin. No client-supplied
    role claim is accepted here.
    """
    deny = lambda reason: RecoveryAuditPreflight(False, reason)
    if not isinstance(record, RecoveryAuditRecord):
        return deny("invalid audit record")
    if not isinstance(authenticated_actor_id, UUID):
        return deny("authenticated actor required")
    if authenticated_actor_id != record.actor_id or record.actor_id != record.target_user_id:
        return deny("actor or target mismatch")
    if not callable(resolve_admin) or resolve_admin(authenticated_actor_id) is not True:
        return deny("trusted admin verification required")
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT a.status, r.kakao_sent_at
            FROM public.kakao_delivery_attempts AS a
            LEFT JOIN public.morning_reports AS r
              ON r.user_id = a.user_id AND r.report_date = a.report_date
            WHERE a.user_id = :user_id AND a.attempt_id = :attempt_id
        """), {"user_id": record.target_user_id, "attempt_id": record.attempt_id}).mappings().one_or_none()
    if row is None:
        return deny("attempt not found for target")
    if row["kakao_sent_at"] is not None:
        return deny("legacy delivery already recorded")
    if record.decision == "eligible_for_future_recovery" and row["status"] != "failed_before_send":
        return deny("attempt is not a confirmed pre-send failure")
    if record.decision not in ("eligible_for_future_recovery", "denied"):
        return deny("invalid audit decision")
    return RecoveryAuditPreflight(True, "read-only preflight passed; no persistence or send authorized")
