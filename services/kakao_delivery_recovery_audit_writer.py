"""Staged, server-only append-only recovery audit writer.

This only records a review. It cannot release a delivery claim or send Kakao.
No API route calls this function. Requires a verified admin session from the
caller and the trusted database connection; never accept client role flags.
"""
from uuid import UUID

from sqlalchemy import text

from services.kakao_delivery_recovery_audit import RecoveryAuditRecord


class RecoveryAuditWriteForbidden(PermissionError):
    pass


def append_recovery_audit(engine, *, record: RecoveryAuditRecord,
                          authenticated_admin_id: UUID) -> int:
    if not isinstance(record, RecoveryAuditRecord) or not isinstance(authenticated_admin_id, UUID):
        raise RecoveryAuditWriteForbidden("verified admin and audit record required")
    if authenticated_admin_id != record.actor_id or record.actor_id != record.target_user_id:
        raise RecoveryAuditWriteForbidden("authenticated actor must own the review")
    if record.decision not in ("denied", "eligible_for_future_recovery"):
        raise RecoveryAuditWriteForbidden("invalid decision")
    if not isinstance(record.evidence_reference, str) or not 1 <= len(record.evidence_reference.strip()) <= 256:
        raise RecoveryAuditWriteForbidden("audit evidence reference required")
    if not isinstance(record.reason, str) or not 1 <= len(record.reason) <= 512:
        raise RecoveryAuditWriteForbidden("reason required")

    # Lock the attempt row so status and legacy marker are checked together
    # with the append. A missing row or conflicting marker fails closed.
    with engine.begin() as conn:
        row = conn.execute(text("""
            SELECT a.status, r.kakao_sent_at
            FROM public.kakao_delivery_attempts AS a
            JOIN public.morning_reports AS r
              ON r.user_id = a.user_id AND r.report_date = a.report_date
            WHERE a.user_id = :user_id AND a.attempt_id = :attempt_id
            FOR UPDATE OF a, r
        """), {"user_id": record.target_user_id, "attempt_id": record.attempt_id}).mappings().one_or_none()
        if row is None or row["kakao_sent_at"] is not None:
            raise RecoveryAuditWriteForbidden("attempt missing or already sent")
        if record.decision == "eligible_for_future_recovery" and row["status"] != "failed_before_send":
            raise RecoveryAuditWriteForbidden("only pre-send failures qualify for review")
        audit_id = conn.execute(text("""
            INSERT INTO public.kakao_delivery_recovery_audit
              (actor_id, target_user_id, attempt_id, reviewed_at,
               evidence_reference, decision, reason)
            VALUES (:actor_id, :target_user_id, :attempt_id, :reviewed_at,
                    :evidence_reference, :decision, :reason)
            RETURNING id
        """), {
            "actor_id": record.actor_id, "target_user_id": record.target_user_id,
            "attempt_id": record.attempt_id, "reviewed_at": record.reviewed_at,
            "evidence_reference": record.evidence_reference,
            "decision": record.decision, "reason": record.reason,
        }).scalar_one()
    return audit_id
