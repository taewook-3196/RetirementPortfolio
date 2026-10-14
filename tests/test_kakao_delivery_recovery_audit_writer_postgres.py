"""Transactional recovery audit writer checks in a disposable PostgreSQL DB."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

from services.kakao_delivery_recovery_audit import RecoveryAuditRecord
from services.kakao_delivery_recovery_audit_writer import (
    RecoveryAuditWriteForbidden, RecoveryAuditDuplicate, append_recovery_audit,
)
from tests.test_kakao_delivery_postgres import pg

pytestmark = pytest.mark.skipif(
    not os.getenv("KAKAO_DELIVERY_TEST_DSN"),
    reason="Disposable PostgreSQL DSN not configured",
)


def test_audit_writer_commit_and_rejected_write_rollback(pg):
    with pg.begin() as conn:
        conn.exec_driver_sql(Path(
            "database/migrations/20261014_kakao_delivery_recovery_audit.sql"
        ).read_text(encoding="utf-8"))
        user, attempt = uuid4(), uuid4()
        conn.execute(text("INSERT INTO public.profiles(id) VALUES (:u)"), {"u": str(user)})
        conn.execute(text("""INSERT INTO public.morning_reports(user_id,report_date)
            VALUES (CAST(:u AS uuid), DATE '2026-10-12')"""), {"u": str(user)})
        assert conn.execute(text("""SELECT public.claim_kakao_delivery_attempt(
            CAST(:u AS uuid), DATE '2026-10-12', CAST(:a AS uuid), 300)"""),
            {"u": str(user), "a": str(attempt)}).scalar_one() is not None
        assert conn.execute(text("""SELECT public.finish_kakao_delivery_attempt(
            CAST(:u AS uuid), CAST(:a AS uuid), 'failed_before_send', NULL)"""),
            {"u": str(user), "a": str(attempt)}).scalar_one() is True

    def make_record():
        return RecoveryAuditRecord(
            actor_id=user, target_user_id=user, attempt_id=attempt,
            reviewed_at=datetime.now(timezone.utc),
            evidence_reference="incident-123",
            decision="denied",
            reason="request start not independently verified",
        )

    def submit(_):
        try:
            return append_recovery_audit(pg, record=make_record(), authenticated_admin_id=user)
        except RecoveryAuditDuplicate:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(submit, range(2)))
    assert sum(isinstance(value, int) for value in outcomes) == 1
    audit_id = next(value for value in outcomes if isinstance(value, int))
    assert isinstance(audit_id, int) and audit_id > 0
    # Duplicate requests are rejected by the DB unique index, not by a
    # race-prone read-before-insert check.
    with pytest.raises(RecoveryAuditDuplicate):
        append_recovery_audit(pg, record=make_record(), authenticated_admin_id=user)
    with pg.begin() as conn:
        assert conn.execute(text("""SELECT count(*) FROM
            public.kakao_delivery_recovery_audit""")).scalar_one() == 1
        # A recorded approval is never permission for another claim.
        assert conn.execute(text("""SELECT public.claim_kakao_delivery_attempt(
            CAST(:u AS uuid), DATE '2026-10-12', CAST(:a AS uuid), 300)"""),
            {"u": str(user), "a": str(uuid4())}).scalar_one() is None
        conn.execute(text("""UPDATE public.morning_reports
            SET kakao_sent_at = now() WHERE user_id = CAST(:u AS uuid)"""),
            {"u": str(user)})

    with pytest.raises(RecoveryAuditWriteForbidden):
        append_recovery_audit(pg, record=make_record(), authenticated_admin_id=user)
    with pg.begin() as conn:
        assert conn.execute(text("""SELECT count(*) FROM
            public.kakao_delivery_recovery_audit""")).scalar_one() == 1
        conn.execute(text("DROP TABLE public.kakao_delivery_recovery_audit"))
        conn.execute(text("DROP FUNCTION public.reject_kakao_recovery_audit_mutation()"))
