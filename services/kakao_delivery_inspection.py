"""Read-only inspection of staged Kakao delivery attempts.

Intended for trusted server-side operators only; never expose directly to clients.
"""

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import text


@dataclass(frozen=True)
class DeliveryInspection:
    user_id: UUID
    report_date: date
    status: str
    legacy_sent: bool
    requires_review: bool


def inspect_delivery_attempts(engine, *, user_id: UUID, limit: int = 30) -> list[DeliveryInspection]:
    """Return minimal non-sensitive delivery metadata for one user only."""
    if not isinstance(user_id, UUID):
        raise ValueError("user_id must be a UUID")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    from services.kakao_delivery_marker_audit import assess_delivery_markers
    from services.kakao_delivery_reconciliation import advise_reconciliation

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT a.user_id, a.report_date, a.status,
                   (r.kakao_sent_at IS NOT NULL) AS legacy_sent
            FROM public.kakao_delivery_attempts AS a
            LEFT JOIN public.morning_reports AS r
              ON r.user_id = a.user_id AND r.report_date = a.report_date
            WHERE a.user_id = :user_id
            ORDER BY a.report_date DESC, a.created_at DESC
            LIMIT :limit
        """), {"user_id": user_id, "limit": limit}).mappings().all()
    result = []
    for row in rows:
        audit = assess_delivery_markers(legacy_sent=row["legacy_sent"], new_status=row["status"])
        advice = advise_reconciliation(attempt_status=row["status"], legacy_sent=row["legacy_sent"])
        result.append(DeliveryInspection(
            user_id=row["user_id"], report_date=row["report_date"], status=row["status"],
            legacy_sent=row["legacy_sent"],
            requires_review=audit.requires_review or advice.needs_reconciliation if hasattr(advice, "needs_reconciliation") else audit.requires_review or advice.action.value == "verify_externally",
        ))
    return result
