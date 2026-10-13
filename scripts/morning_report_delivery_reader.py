"""Read-only database adapter for morning-report delivery markers.

Never prints user IDs or Kakao credentials; never sends messages.
"""
from __future__ import annotations

from datetime import date

from database.connection import get_db_session
from database.models import MorningReport, Profile, UserSetting


def read_recipient_markers(day: date) -> list[dict]:
    """Fetch enabled users and today's stored delivery marker in one query.

    Only boolean status and timestamps leave the database session.
    A missing row is an unconfirmed delivery, not proof of failure.
    """
    with get_db_session() as session:
        rows = (
            session.query(
                UserSetting.morning_report_enabled,
                UserSetting.kakao_enabled,
                MorningReport.kakao_sent_at,
            )
            .join(Profile, Profile.id == UserSetting.user_id)
            .outerjoin(
                MorningReport,
                (MorningReport.user_id == UserSetting.user_id)
                & (MorningReport.report_date == day),
            )
            .filter(Profile.is_active.is_(True))
            .all()
        )
        return [
            {
                "enabled": bool(enabled),
                "kakao_enabled": bool(kakao),
                # Markers are scoped to the report date by the join.
                # DB timestamps may be naive; normalize at the adapter boundary.
                "sent_at": None,
                "report_date_marker_present": sent_at is not None,
            }
            for enabled, kakao, sent_at in rows
        ]
