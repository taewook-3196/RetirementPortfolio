"""PostgreSQL-only integration checks for Kakao delivery claims.

Run with KAKAO_DELIVERY_TEST_DSN pointed at a disposable PostgreSQL database.
Never use a production database: this test creates and drops public objects.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

DSN = os.getenv("KAKAO_DELIVERY_TEST_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL DSN not configured")


@pytest.fixture
def pg():
    db_name = make_url(DSN).database
    if db_name != "kakao_delivery_ci":
        pytest.fail("Refusing to modify a database other than kakao_delivery_ci")
    engine = create_engine(DSN, pool_size=5, max_overflow=5)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS public.profiles (id uuid PRIMARY KEY)"))
        sql = Path("database/migrations/20261012_kakao_delivery_attempts.sql").read_text(encoding="utf-8")
        conn.exec_driver_sql(sql)
    yield engine
    with engine.begin() as conn:
        conn.execute(text("DROP FUNCTION IF EXISTS public.finish_kakao_delivery_attempt(uuid, uuid, text, text)"))
        conn.execute(text("DROP FUNCTION IF EXISTS public.claim_kakao_delivery_attempt(uuid, date, uuid, integer)"))
        conn.execute(text("DROP TABLE IF EXISTS public.kakao_delivery_attempts"))
        conn.execute(text("DROP TABLE IF EXISTS public.profiles"))
    engine.dispose()


def test_concurrent_claims_allow_only_one_worker(pg):
    user_id = uuid4()
    with pg.begin() as conn:
        conn.execute(text("INSERT INTO public.profiles (id) VALUES (:id)"), {"id": str(user_id)})

    def claim(_):
        with pg.begin() as conn:
            return conn.execute(
                text("SELECT public.claim_kakao_delivery_attempt(CAST(:u AS uuid), CAST(:d AS date), CAST(:a AS uuid), 300)"),
                {"u": str(user_id), "d": "2026-10-12", "a": str(uuid4())},
            ).scalar_one()

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(claim, range(4)))
    assert sum(value is not None for value in results) == 1


def test_only_claim_owner_can_finalize(pg):
    user_id, attempt_id = uuid4(), uuid4()
    with pg.begin() as conn:
        conn.execute(text("INSERT INTO public.profiles (id) VALUES (:id)"), {"id": str(user_id)})
        claim = conn.execute(
            text("SELECT public.claim_kakao_delivery_attempt(CAST(:u AS uuid), CAST(:d AS date), CAST(:a AS uuid), 300)"),
            {"u": str(user_id), "d": "2026-10-12", "a": str(attempt_id)},
        ).scalar_one()
        assert claim is not None
        finish_sql = text("SELECT public.finish_kakao_delivery_attempt(CAST(:u AS uuid), CAST(:a AS uuid), :status, NULL)")
        assert conn.execute(finish_sql, {"u": str(user_id), "a": str(uuid4()), "status": "sent"}).scalar_one() is False
        assert conn.execute(finish_sql, {"u": str(user_id), "a": str(attempt_id), "status": "sent"}).scalar_one() is True
        assert conn.execute(finish_sql, {"u": str(user_id), "a": str(attempt_id), "status": "uncertain"}).scalar_one() is False
