"""Staged-only validator for cached Kakao delivery identity.

Legacy .kakao_payload.json has no trustworthy user/date binding and must not
be sent through the claim-backed dispatcher without a verified report row.
No production entrypoint imports this module.
"""
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import text


@dataclass(frozen=True)
class VerifiedCachedReport:
    user_id: UUID
    report_date: date
    legacy_sent: bool
    attempt_state: str | None


def verify_cached_report_identity(*, engine, user_id, report_date):
    """Fail closed unless the exact persisted user/date report is unambiguous.

    This is a read-only preflight, not send authorization. The database claim
    remains authoritative and must be acquired after this preflight.
    """
    if not isinstance(user_id, UUID) or type(report_date) is not date:
        return None
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT kakao_sent_at FROM public.morning_reports "
                "WHERE user_id = :user_id AND report_date = :report_date"
            ),
            {"user_id": user_id, "report_date": report_date},
        ).fetchall()
        if len(rows) != 1:
            return None
        states = conn.execute(
            text(
                "SELECT status FROM public.kakao_delivery_attempts "
                "WHERE user_id = :user_id AND report_date = :report_date"
            ),
            {"user_id": user_id, "report_date": report_date},
        ).fetchall()
        if len(states) > 1:
            return None
        return VerifiedCachedReport(
            user_id=user_id,
            report_date=report_date,
            legacy_sent=rows[0][0] is not None,
            attempt_state=states[0][0] if states else None,
        )
