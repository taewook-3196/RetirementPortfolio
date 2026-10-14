"""Disposable PostgreSQL checks for the staged recovery audit migration."""
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
import os

pytestmark = pytest.mark.skipif(not os.getenv("KAKAO_DELIVERY_TEST_DSN"), reason="Disposable PostgreSQL DSN not configured")

from tests.test_kakao_delivery_postgres import pg  # same guarded disposable fixture


def test_recovery_audit_append_only_and_client_roles_denied(pg):
    sql = Path("database/migrations/20261014_kakao_delivery_recovery_audit.sql").read_text()
    with pg.begin() as conn:
        conn.exec_driver_sql(sql)
        user, attempt = uuid4(), uuid4()
        conn.execute(text("INSERT INTO public.profiles(id) VALUES (:u)"), {"u": str(user)})
        conn.execute(text("INSERT INTO public.morning_reports(user_id,report_date) VALUES (CAST(:u AS uuid), DATE '2026-10-12')"), {"u": str(user)})
        conn.execute(text("SELECT public.claim_kakao_delivery_attempt(CAST(:u AS uuid), DATE '2026-10-12', CAST(:a AS uuid), 300)"), {"u": str(user), "a": str(attempt)})
        conn.execute(text("""INSERT INTO public.kakao_delivery_recovery_audit
            (actor_id,target_user_id,attempt_id,reviewed_at,evidence_reference,decision,reason)
            VALUES (CAST(:u AS uuid),CAST(:u AS uuid),CAST(:a AS uuid),now(),'ticket-1','denied','not proven')"""), {"u": str(user), "a": str(attempt)})
        for role in ("anon", "authenticated"):
            assert conn.execute(text("SELECT has_table_privilege(:r, 'public.kakao_delivery_recovery_audit', 'SELECT')"), {"r": role}).scalar_one() is False
            assert conn.execute(text("SELECT has_table_privilege(:r, 'public.kakao_delivery_recovery_audit', 'INSERT')"), {"r": role}).scalar_one() is False
        assert conn.execute(text("SELECT relrowsecurity FROM pg_class WHERE oid = 'public.kakao_delivery_recovery_audit'::regclass")).scalar_one() is True
    with pytest.raises(Exception, match="append-only"):
        with pg.begin() as conn:
            conn.execute(text("DELETE FROM public.kakao_delivery_recovery_audit"))
    with pg.begin() as conn:
        conn.execute(text("DROP TABLE public.kakao_delivery_recovery_audit"))
        conn.execute(text("DROP FUNCTION public.reject_kakao_recovery_audit_mutation()"))
