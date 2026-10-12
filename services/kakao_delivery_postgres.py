"""Transactional PostgreSQL adapter for staged Kakao delivery attempts.

This module is not imported by the production sender. Callers must supply
an authenticated trusted backend SQLAlchemy engine; never a client credential.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text


@dataclass(frozen=True)
class DeliveryAttempt:
    user_id: UUID
    report_date: object
    attempt_id: UUID


class PostgresDeliveryAttempts:
    def __init__(self, engine):
        self.engine = engine

    def claim(self, attempt: DeliveryAttempt, lease_seconds: int = 300):
        """Return claim ID only after commit; exceptions prevent any sending."""
        with self.engine.begin() as conn:
            claim_id = conn.execute(
                text("SELECT public.claim_kakao_delivery_attempt(:user_id, :report_date, :attempt_id, :lease_seconds)"),
                {"user_id": attempt.user_id, "report_date": attempt.report_date,
                 "attempt_id": attempt.attempt_id, "lease_seconds": lease_seconds},
            ).scalar_one()
        return claim_id

    def finish(self, attempt: DeliveryAttempt, status: str, error_code=None) -> bool:
        """Only the exact claim owner can finalize; false means reconciliation."""
        if status not in ("sent", "uncertain", "failed_before_send"):
            raise ValueError("invalid delivery completion status")
        with self.engine.begin() as conn:
            result = conn.execute(
                text("SELECT public.finish_kakao_delivery_attempt(:user_id, :attempt_id, :status, :error_code)"),
                {"user_id": attempt.user_id, "attempt_id": attempt.attempt_id,
                 "status": status, "error_code": error_code},
            ).scalar_one()
        return result is True
