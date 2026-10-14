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
        conn.execute(text("CREATE ROLE anon NOLOGIN"))
        conn.execute(text("CREATE ROLE authenticated NOLOGIN"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS public.profiles (id uuid PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE public.morning_reports (user_id uuid NOT NULL, report_date date NOT NULL, kakao_sent_at timestamptz, updated_at timestamptz, UNIQUE (user_id, report_date))"))
        sql = Path("database/migrations/20261012_kakao_delivery_attempts.sql").read_text(encoding="utf-8")
        conn.exec_driver_sql(sql)
    yield engine
    with engine.begin() as conn:
        conn.execute(text("DROP FUNCTION IF EXISTS public.finish_kakao_delivery_with_legacy(uuid, uuid)"))
        conn.execute(text("DROP FUNCTION IF EXISTS public.finish_kakao_delivery_attempt(uuid, uuid, text, text)"))
        conn.execute(text("DROP FUNCTION IF EXISTS public.claim_kakao_delivery_attempt(uuid, date, uuid, integer)"))
        conn.execute(text("DROP TABLE IF EXISTS public.kakao_delivery_recovery_audit"))
        conn.execute(text("DROP FUNCTION IF EXISTS public.reject_kakao_recovery_audit_mutation()"))
        conn.execute(text("DROP TABLE IF EXISTS public.kakao_delivery_attempts"))
        conn.execute(text("DROP TABLE IF EXISTS public.morning_reports"))
        conn.execute(text("DROP TABLE IF EXISTS public.profiles"))
        conn.execute(text("DROP ROLE IF EXISTS anon"))
        conn.execute(text("DROP ROLE IF EXISTS authenticated"))
    engine.dispose()


def test_concurrent_claims_allow_only_one_worker(pg):
    user_id = uuid4()
    with pg.begin() as conn:
        conn.execute(text("INSERT INTO public.profiles (id) VALUES (:id)"), {"id": str(user_id)})
        conn.execute(text("INSERT INTO public.morning_reports (user_id, report_date) VALUES (CAST(:u AS uuid), DATE '2026-10-12') ON CONFLICT DO NOTHING"), {"u": str(user_id)})

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
        conn.execute(text("INSERT INTO public.morning_reports (user_id, report_date) VALUES (CAST(:u AS uuid), DATE '2026-10-12') ON CONFLICT DO NOTHING"), {"u": str(user_id)})
        claim = conn.execute(
            text("SELECT public.claim_kakao_delivery_attempt(CAST(:u AS uuid), CAST(:d AS date), CAST(:a AS uuid), 300)"),
            {"u": str(user_id), "d": "2026-10-12", "a": str(attempt_id)},
        ).scalar_one()
        assert claim is not None
        finish_sql = text("SELECT public.finish_kakao_delivery_attempt(CAST(:u AS uuid), CAST(:a AS uuid), :status, NULL)")
        assert conn.execute(finish_sql, {"u": str(user_id), "a": str(uuid4()), "status": "uncertain"}).scalar_one() is False
        assert conn.execute(text("SELECT public.finish_kakao_delivery_with_legacy(CAST(:u AS uuid), CAST(:a AS uuid))"), {"u": str(user_id), "a": str(attempt_id)}).scalar_one() is True
        assert conn.execute(finish_sql, {"u": str(user_id), "a": str(attempt_id), "status": "uncertain"}).scalar_one() is False


def test_uncertain_outcome_blocks_next_claim_even_after_lease_expiry(pg):
    user_id, attempt_id = uuid4(), uuid4()
    with pg.begin() as conn:
        conn.execute(text("INSERT INTO public.profiles (id) VALUES (:id)"), {"id": str(user_id)})
        conn.execute(text("INSERT INTO public.morning_reports (user_id, report_date) VALUES (CAST(:u AS uuid), DATE '2026-10-12') ON CONFLICT DO NOTHING"), {"u": str(user_id)})
        args = {"u": str(user_id), "d": "2026-10-12", "a": str(attempt_id)}
        claim = text("SELECT public.claim_kakao_delivery_attempt(CAST(:u AS uuid), CAST(:d AS date), CAST(:a AS uuid), 300)")
        assert conn.execute(claim, args).scalar_one() is not None
        conn.execute(text("UPDATE public.kakao_delivery_attempts SET lease_expires_at = now() - interval '1 hour' WHERE attempt_id = CAST(:a AS uuid)"), args)
        assert conn.execute(claim, {**args, "a": str(uuid4())}).scalar_one() is None
        finish = text("SELECT public.finish_kakao_delivery_attempt(CAST(:u AS uuid), CAST(:a AS uuid), :status, NULL)")
        assert conn.execute(finish, {**args, "status": "uncertain"}).scalar_one() is True
        assert conn.execute(claim, {**args, "a": str(uuid4())}).scalar_one() is None


def test_failed_before_send_blocks_new_claim_until_reviewed_recovery(pg):
    user_id, attempt_id = uuid4(), uuid4()
    with pg.begin() as conn:
        conn.execute(text("INSERT INTO public.profiles (id) VALUES (:id)"), {"id": str(user_id)})
        conn.execute(text("INSERT INTO public.morning_reports (user_id, report_date) VALUES (CAST(:u AS uuid), DATE '2026-10-12') ON CONFLICT DO NOTHING"), {"u": str(user_id)})
        args = {"u": str(user_id), "d": "2026-10-12", "a": str(attempt_id)}
        claim = text("SELECT public.claim_kakao_delivery_attempt(CAST(:u AS uuid), CAST(:d AS date), CAST(:a AS uuid), 300)")
        assert conn.execute(claim, args).scalar_one() is not None
        finish = text("SELECT public.finish_kakao_delivery_attempt(CAST(:u AS uuid), CAST(:a AS uuid), :status, NULL)")
        assert conn.execute(finish, {**args, "status": "failed_before_send"}).scalar_one() is True
        assert conn.execute(claim, {**args, "a": str(uuid4())}).scalar_one() is None


def test_legacy_sent_marker_prevents_new_claim(pg):
    user_id = uuid4()
    with pg.begin() as conn:
        conn.execute(text("INSERT INTO public.profiles (id) VALUES (:id)"), {"id": str(user_id)})
        conn.execute(text("INSERT INTO public.morning_reports (user_id, report_date) VALUES (CAST(:u AS uuid), DATE '2026-10-12') ON CONFLICT DO NOTHING"), {"u": str(user_id)})
        conn.execute(text("INSERT INTO public.morning_reports (user_id, report_date, kakao_sent_at) VALUES (CAST(:u AS uuid), DATE '2026-10-12', now()) ON CONFLICT (user_id, report_date) DO UPDATE SET kakao_sent_at = EXCLUDED.kakao_sent_at"), {"u": str(user_id)})
        result = conn.execute(
            text("SELECT public.claim_kakao_delivery_attempt(CAST(:u AS uuid), DATE '2026-10-12', CAST(:a AS uuid), 300)"),
            {"u": str(user_id), "a": str(uuid4())},
        ).scalar_one()
        assert result is None


def test_adapter_commits_claim_and_owner_completion(pg):
    from datetime import date
    from services.kakao_delivery_postgres import DeliveryAttempt, PostgresDeliveryAttempts

    user_id, attempt_id = uuid4(), uuid4()
    with pg.begin() as conn:
        conn.execute(text("INSERT INTO public.profiles (id) VALUES (:id)"), {"id": str(user_id)})
        conn.execute(text("INSERT INTO public.morning_reports (user_id, report_date) VALUES (CAST(:u AS uuid), DATE '2026-10-12') ON CONFLICT DO NOTHING"), {"u": str(user_id)})
    adapter = PostgresDeliveryAttempts(pg)
    attempt = DeliveryAttempt(user_id=user_id, report_date=date(2026, 10, 12), attempt_id=attempt_id)
    assert adapter.claim(attempt) is not None
    assert adapter.claim(DeliveryAttempt(user_id, date(2026, 10, 12), uuid4())) is None
    assert adapter.finish_sent_with_legacy(attempt) is True
    assert adapter.finish(attempt, "uncertain") is False


def test_adapter_claim_rejects_already_sent_legacy_report(pg):
    from datetime import date
    from services.kakao_delivery_postgres import DeliveryAttempt, PostgresDeliveryAttempts

    user_id = uuid4()
    with pg.begin() as conn:
        conn.execute(text("INSERT INTO public.profiles (id) VALUES (:id)"), {"id": str(user_id)})
        conn.execute(text("INSERT INTO public.morning_reports (user_id, report_date) VALUES (CAST(:u AS uuid), DATE '2026-10-12') ON CONFLICT DO NOTHING"), {"u": str(user_id)})
        conn.execute(text("INSERT INTO public.morning_reports (user_id, report_date, kakao_sent_at) VALUES (CAST(:u AS uuid), DATE '2026-10-12', now()) ON CONFLICT (user_id, report_date) DO UPDATE SET kakao_sent_at = EXCLUDED.kakao_sent_at"), {"u": str(user_id)})
    assert PostgresDeliveryAttempts(pg).claim(DeliveryAttempt(user_id, date(2026, 10, 12), uuid4())) is None


def test_staged_delivery_sends_only_once_with_mock_transport(pg):
    from datetime import date
    from services.kakao_delivery_staged import run_staged_delivery
    from services.kakao_delivery_orchestrator import SendOutcome

    user_id = uuid4()
    with pg.begin() as conn:
        conn.execute(text("INSERT INTO public.profiles (id) VALUES (:id)"), {"id": str(user_id)})
        conn.execute(text("INSERT INTO public.morning_reports (user_id, report_date) VALUES (CAST(:u AS uuid), DATE '2026-10-12') ON CONFLICT DO NOTHING"), {"u": str(user_id)})
    with pg.begin() as conn:
        conn.execute(text("INSERT INTO public.morning_reports (user_id, report_date) VALUES (CAST(:u AS uuid), DATE '2026-10-12') ON CONFLICT DO NOTHING"), {"u": str(user_id)})
    events = []
    env = {"KAKAO_DELIVERY_STATE_ENABLED": "true", "KAKAO_DELIVERY_CUTOVER_APPROVED": "true"}
    first = run_staged_delivery(engine=pg, user_id=user_id, report_date=date(2026, 10, 12), transport=lambda: events.append("sent") or (True, "mock"), env=env)
    second = run_staged_delivery(engine=pg, user_id=user_id, report_date=date(2026, 10, 12), transport=lambda: events.append("duplicate"), env=env)
    assert first.outcome == SendOutcome.SENT
    assert second.outcome == SendOutcome.NOT_CLAIMED
    assert events == ["sent"]
    with pg.connect() as conn:
        assert conn.execute(text("SELECT kakao_sent_at FROM public.morning_reports WHERE user_id = CAST(:u AS uuid)"), {"u": str(user_id)}).scalar_one() is not None


def test_staged_delivery_off_never_claims_or_sends(pg):
    from datetime import date
    from services.kakao_delivery_staged import run_staged_delivery
    from services.kakao_delivery_orchestrator import SendOutcome

    result = run_staged_delivery(engine=pg, user_id=uuid4(), report_date=date(2026, 10, 12), transport=lambda: pytest.fail("sent"), env={})
    assert result.outcome == SendOutcome.DISABLED


def test_staged_delivery_timeout_blocks_second_mock_send(pg):
    from datetime import date
    from services.kakao_delivery_staged import run_staged_delivery
    from services.kakao_delivery_orchestrator import SendOutcome

    user_id = uuid4()
    with pg.begin() as conn:
        conn.execute(text("INSERT INTO public.profiles (id) VALUES (:id)"), {"id": str(user_id)})
        conn.execute(text("INSERT INTO public.morning_reports (user_id, report_date) VALUES (CAST(:u AS uuid), DATE '2026-10-12') ON CONFLICT DO NOTHING"), {"u": str(user_id)})
    env = {"KAKAO_DELIVERY_STATE_ENABLED": "true", "KAKAO_DELIVERY_CUTOVER_APPROVED": "true"}
    def timeout():
        raise TimeoutError("lost response after request")
    first = run_staged_delivery(engine=pg, user_id=user_id, report_date=date(2026, 10, 12), transport=timeout, env=env)
    second = run_staged_delivery(engine=pg, user_id=user_id, report_date=date(2026, 10, 12), transport=lambda: pytest.fail("duplicate"), env=env)
    assert first.outcome == SendOutcome.UNCERTAIN
    assert second.outcome == SendOutcome.NOT_CLAIMED


def test_client_roles_cannot_access_attempts_or_execute_functions(pg):
    with pg.connect() as conn:
        for role in ("anon", "authenticated"):
            assert conn.execute(text("SELECT has_table_privilege(:role, 'public.kakao_delivery_attempts', 'SELECT')"), {"role": role}).scalar_one() is False
            assert conn.execute(text("SELECT has_table_privilege(:role, 'public.kakao_delivery_attempts', 'INSERT')"), {"role": role}).scalar_one() is False
            assert conn.execute(text("SELECT has_table_privilege(:role, 'public.kakao_delivery_attempts', 'UPDATE')"), {"role": role}).scalar_one() is False
            assert conn.execute(text("SELECT has_function_privilege(:role, 'public.claim_kakao_delivery_attempt(uuid,date,uuid,integer)', 'EXECUTE')"), {"role": role}).scalar_one() is False
            assert conn.execute(text("SELECT has_function_privilege(:role, 'public.finish_kakao_delivery_attempt(uuid,uuid,text,text)', 'EXECUTE')"), {"role": role}).scalar_one() is False
            assert conn.execute(text("SELECT has_function_privilege(:role, 'public.finish_kakao_delivery_with_legacy(uuid,uuid)', 'EXECUTE')"), {"role": role}).scalar_one() is False
        assert conn.execute(text("SELECT relrowsecurity FROM pg_class WHERE oid = 'public.kakao_delivery_attempts'::regclass")).scalar_one() is True


def test_attempts_are_isolated_by_user_and_date(pg):
    from datetime import date
    from services.kakao_delivery_postgres import DeliveryAttempt, PostgresDeliveryAttempts

    a, b = uuid4(), uuid4()
    with pg.begin() as conn:
        conn.execute(text("INSERT INTO public.profiles (id) VALUES (:a), (:b)"), {"a": str(a), "b": str(b)})
        conn.execute(text("INSERT INTO public.morning_reports (user_id, report_date) VALUES (CAST(:a AS uuid), DATE '2026-10-12'), (CAST(:b AS uuid), DATE '2026-10-12') ON CONFLICT DO NOTHING"), {"a": str(a), "b": str(b)})
    adapter = PostgresDeliveryAttempts(pg)
    a_attempt = DeliveryAttempt(a, date(2026, 10, 12), uuid4())
    b_attempt = DeliveryAttempt(b, date(2026, 10, 12), uuid4())
    with pg.begin() as conn:
        conn.execute(text("INSERT INTO public.morning_reports (user_id, report_date) VALUES (CAST(:a AS uuid), DATE '2026-10-13')"), {"a": str(a)})
    next_day = DeliveryAttempt(a, date(2026, 10, 13), uuid4())
    assert adapter.claim(a_attempt) is not None
    assert adapter.claim(b_attempt) is not None
    assert adapter.claim(next_day) is not None
    assert adapter.finish_sent_with_legacy(DeliveryAttempt(b, date(2026, 10, 12), a_attempt.attempt_id)) is False
    assert adapter.finish_sent_with_legacy(a_attempt) is True
    assert adapter.finish_sent_with_legacy(b_attempt) is True


def test_atomic_dual_marker_completion(pg):
    from datetime import date
    from services.kakao_delivery_postgres import DeliveryAttempt, PostgresDeliveryAttempts
    user_id = uuid4()
    with pg.begin() as conn:
        conn.execute(text("INSERT INTO public.profiles (id) VALUES (:u)"), {"u": str(user_id)})
        conn.execute(text("INSERT INTO public.morning_reports (user_id, report_date) VALUES (CAST(:u AS uuid), DATE '2026-10-12') ON CONFLICT DO NOTHING"), {"u": str(user_id)})
        conn.execute(text("INSERT INTO public.morning_reports (user_id, report_date) VALUES (CAST(:u AS uuid), DATE '2026-10-12') ON CONFLICT DO NOTHING"), {"u": str(user_id)})
    attempt = DeliveryAttempt(user_id, date(2026, 10, 12), uuid4())
    assert PostgresDeliveryAttempts(pg).claim(attempt) is not None
    with pg.begin() as conn:
        assert conn.execute(text("SELECT public.finish_kakao_delivery_with_legacy(CAST(:u AS uuid), CAST(:a AS uuid))"), {"u": str(user_id), "a": str(attempt.attempt_id)}).scalar_one() is True
        legacy = conn.execute(text("SELECT kakao_sent_at FROM public.morning_reports WHERE user_id = CAST(:u AS uuid)"), {"u": str(user_id)}).scalar_one()
        status = conn.execute(text("SELECT status FROM public.kakao_delivery_attempts WHERE attempt_id = CAST(:a AS uuid)"), {"a": str(attempt.attempt_id)}).scalar_one()
        assert legacy is not None
        assert status == "sent"


def test_missing_legacy_row_never_marks_attempt_sent(pg):
    from datetime import date
    from services.kakao_delivery_postgres import DeliveryAttempt, PostgresDeliveryAttempts
    user_id = uuid4()
    with pg.begin() as conn:
        conn.execute(text("INSERT INTO public.profiles (id) VALUES (:u)"), {"u": str(user_id)})
        conn.execute(text("INSERT INTO public.morning_reports (user_id, report_date) VALUES (CAST(:u AS uuid), DATE '2026-10-12') ON CONFLICT DO NOTHING"), {"u": str(user_id)})
    attempt = DeliveryAttempt(user_id, date(2026, 10, 12), uuid4())
    assert PostgresDeliveryAttempts(pg).claim(attempt) is not None
    with pg.begin() as conn:
        conn.execute(text("DELETE FROM public.morning_reports WHERE user_id = CAST(:u AS uuid)"), {"u": str(user_id)})
        assert conn.execute(text("SELECT public.finish_kakao_delivery_with_legacy(CAST(:u AS uuid), CAST(:a AS uuid))"), {"u": str(user_id), "a": str(attempt.attempt_id)}).scalar_one() is False
        assert conn.execute(text("SELECT status FROM public.kakao_delivery_attempts WHERE attempt_id = CAST(:a AS uuid)"), {"a": str(attempt.attempt_id)}).scalar_one() == "sending"



def test_staged_success_without_legacy_report_is_uncertain_and_not_retried(pg):
    from datetime import date
    from services.kakao_delivery_staged import run_staged_delivery
    from services.kakao_delivery_orchestrator import SendOutcome

    user_id = uuid4()
    with pg.begin() as conn:
        conn.execute(text("INSERT INTO public.profiles (id) VALUES (:u)"), {"u": str(user_id)})
        conn.execute(text("INSERT INTO public.morning_reports (user_id, report_date) VALUES (CAST(:u AS uuid), DATE '2026-10-12') ON CONFLICT DO NOTHING"), {"u": str(user_id)})
    env = {"KAKAO_DELIVERY_STATE_ENABLED": "true", "KAKAO_DELIVERY_CUTOVER_APPROVED": "true"}
    events = []
    def accepted_then_report_disappears():
        events.append("first")
        with pg.begin() as conn:
            conn.execute(text("DELETE FROM public.morning_reports WHERE user_id = CAST(:u AS uuid) AND report_date = DATE '2026-10-12'"), {"u": str(user_id)})
        return True, "ok"

    first = run_staged_delivery(
        engine=pg, user_id=user_id, report_date=date(2026, 10, 12),
        transport=accepted_then_report_disappears, env=env,
    )
    second = run_staged_delivery(
        engine=pg, user_id=user_id, report_date=date(2026, 10, 12),
        transport=lambda: events.append("duplicate") or (True, "ok"), env=env,
    )
    assert first.outcome == SendOutcome.UNCERTAIN
    assert first.needs_reconciliation
    assert second.outcome == SendOutcome.NOT_CLAIMED
    assert events == ["first"]
    with pg.connect() as conn:
        assert conn.execute(
            text("SELECT status FROM public.kakao_delivery_attempts WHERE user_id = CAST(:u AS uuid)"),
            {"u": str(user_id)},
        ).scalar_one() == "sending"


def test_staged_transport_failure_preserves_legacy_unsent_and_blocks_retry(pg):
    from datetime import date
    from services.kakao_delivery_staged import run_staged_delivery
    from services.kakao_delivery_orchestrator import SendOutcome

    user_id = uuid4()
    with pg.begin() as conn:
        conn.execute(text("INSERT INTO public.profiles (id) VALUES (:u)"), {"u": str(user_id)})
        conn.execute(text("INSERT INTO public.morning_reports (user_id, report_date) VALUES (CAST(:u AS uuid), DATE '2026-10-12') ON CONFLICT DO NOTHING"), {"u": str(user_id)})
        conn.execute(text("INSERT INTO public.morning_reports (user_id, report_date) VALUES (CAST(:u AS uuid), DATE '2026-10-12') ON CONFLICT DO NOTHING"), {"u": str(user_id)})
    env = {"KAKAO_DELIVERY_STATE_ENABLED": "true", "KAKAO_DELIVERY_CUTOVER_APPROVED": "true"}
    events = []
    first = run_staged_delivery(
        engine=pg, user_id=user_id, report_date=date(2026, 10, 12),
        transport=lambda: events.append("first") or (False, "timeout"), env=env,
    )
    second = run_staged_delivery(
        engine=pg, user_id=user_id, report_date=date(2026, 10, 12),
        transport=lambda: events.append("duplicate"), env=env,
    )
    assert first.outcome == SendOutcome.UNCERTAIN
    assert second.outcome == SendOutcome.NOT_CLAIMED
    assert events == ["first"]
    with pg.connect() as conn:
        assert conn.execute(
            text("SELECT kakao_sent_at FROM public.morning_reports WHERE user_id = CAST(:u AS uuid)"),
            {"u": str(user_id)},
        ).scalar_one() is None
        assert conn.execute(
            text("SELECT status FROM public.kakao_delivery_attempts WHERE user_id = CAST(:u AS uuid)"),
            {"u": str(user_id)},
        ).scalar_one() == "uncertain"


def test_read_only_inspection_is_scoped_and_flags_uncertain(pg):
    from datetime import date
    from services.kakao_delivery_postgres import DeliveryAttempt, PostgresDeliveryAttempts
    from services.kakao_delivery_inspection import inspect_delivery_attempts

    a, b = uuid4(), uuid4()
    with pg.begin() as conn:
        conn.execute(text("INSERT INTO public.profiles (id) VALUES (:a), (:b)"), {"a": str(a), "b": str(b)})
        conn.execute(text("INSERT INTO public.morning_reports (user_id, report_date) VALUES (CAST(:a AS uuid), DATE '2026-10-12'), (CAST(:b AS uuid), DATE '2026-10-12') ON CONFLICT DO NOTHING"), {"a": str(a), "b": str(b)})
    store = PostgresDeliveryAttempts(pg)
    aa = DeliveryAttempt(a, date(2026, 10, 12), uuid4())
    bb = DeliveryAttempt(b, date(2026, 10, 12), uuid4())
    assert store.claim(aa) is not None
    assert store.claim(bb) is not None
    assert store.finish(aa, "uncertain") is True
    rows = inspect_delivery_attempts(pg, user_id=a)
    assert len(rows) == 1
    assert rows[0].user_id == a
    assert rows[0].status == "uncertain"
    assert rows[0].requires_review is True
    assert inspect_delivery_attempts(pg, user_id=b)[0].status == "sending"
    with pg.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM public.kakao_delivery_attempts")).scalar_one() == 2


def test_inspection_rejects_unbounded_or_invalid_queries(pg):
    from services.kakao_delivery_inspection import inspect_delivery_attempts
    with pytest.raises(ValueError):
        inspect_delivery_attempts(pg, user_id=uuid4(), limit=1000)
    with pytest.raises(ValueError):
        inspect_delivery_attempts(pg, user_id=str(uuid4()))


def test_admin_inspection_requires_explicit_permission_and_limits_target(pg):
    from datetime import date
    from services.kakao_delivery_operator_access import inspect_for_operator, DeliveryInspectionForbidden
    from services.kakao_delivery_postgres import DeliveryAttempt, PostgresDeliveryAttempts
    admin, user_a, user_b = uuid4(), uuid4(), uuid4()
    with pg.begin() as conn:
        conn.execute(text("INSERT INTO public.profiles (id) VALUES (:a), (:b)"), {"a": str(user_a), "b": str(user_b)})
        conn.execute(text("INSERT INTO public.morning_reports (user_id, report_date) VALUES (CAST(:a AS uuid), DATE '2026-10-12'), (CAST(:b AS uuid), DATE '2026-10-12') ON CONFLICT DO NOTHING"), {"a": str(user_a), "b": str(user_b)})
    store = PostgresDeliveryAttempts(pg)
    assert store.claim(DeliveryAttempt(user_a, date(2026, 10, 12), uuid4())) is not None
    assert store.claim(DeliveryAttempt(user_b, date(2026, 10, 12), uuid4())) is not None
    with pytest.raises(DeliveryInspectionForbidden):
        inspect_for_operator(pg, actor_id=user_a, actor_is_admin=False, target_user_id=user_b)
    with pytest.raises(DeliveryInspectionForbidden):
        inspect_for_operator(pg, actor_id=admin, actor_is_admin=True, target_user_id=user_a)
    rows = inspect_for_operator(pg, actor_id=user_a, actor_is_admin=True, target_user_id=user_a)
    assert len(rows) == 1
    assert rows[0].user_id == user_a


def test_missing_dated_report_refuses_claim_and_never_calls_transport(pg):
    from datetime import date
    from services.kakao_delivery_staged import run_staged_delivery
    from services.kakao_delivery_orchestrator import SendOutcome

    user_id = uuid4()
    with pg.begin() as conn:
        conn.execute(text("INSERT INTO public.profiles (id) VALUES (:id)"), {"id": str(user_id)})
    events = []
    result = run_staged_delivery(
        engine=pg, user_id=user_id, report_date=date(2026, 10, 12),
        transport=lambda: events.append("send") or (True, "ok"),
        env={"KAKAO_DELIVERY_STATE_ENABLED": "true", "KAKAO_DELIVERY_CUTOVER_APPROVED": "true"},
    )
    assert result.outcome == SendOutcome.NOT_CLAIMED
    assert events == []


def test_atomic_legacy_completion_cannot_finalize_another_users_attempt(pg):
    from datetime import date
    from services.kakao_delivery_postgres import DeliveryAttempt, PostgresDeliveryAttempts

    user_a, user_b = uuid4(), uuid4()
    with pg.begin() as conn:
        conn.execute(text("INSERT INTO public.profiles (id) VALUES (:a), (:b)"), {"a": str(user_a), "b": str(user_b)})
        conn.execute(
            text("INSERT INTO public.morning_reports (user_id, report_date) VALUES (CAST(:a AS uuid), DATE '2026-10-12'), (CAST(:b AS uuid), DATE '2026-10-12')"),
            {"a": str(user_a), "b": str(user_b)},
        )
    attempt = DeliveryAttempt(user_a, date(2026, 10, 12), uuid4())
    adapter = PostgresDeliveryAttempts(pg)
    assert adapter.claim(attempt) is not None
    with pg.begin() as conn:
        assert conn.execute(
            text("SELECT public.finish_kakao_delivery_with_legacy(CAST(:u AS uuid), CAST(:id AS uuid))"),
            {"u": str(user_b), "id": str(attempt.attempt_id)},
        ).scalar_one() is False
        assert conn.execute(
            text("SELECT kakao_sent_at IS NOT NULL FROM public.morning_reports WHERE user_id = CAST(:u AS uuid)"),
            {"u": str(user_b)},
        ).scalar_one() is False
        assert conn.execute(
            text("SELECT status FROM public.kakao_delivery_attempts WHERE attempt_id = CAST(:id AS uuid)"),
            {"id": str(attempt.attempt_id)},
        ).scalar_one() == "sending"
    assert adapter.finish_sent_with_legacy(attempt) is True


def test_atomic_legacy_completion_updates_only_claimed_report_date(pg):
    from datetime import date
    from services.kakao_delivery_postgres import DeliveryAttempt, PostgresDeliveryAttempts

    user_id = uuid4()
    with pg.begin() as conn:
        conn.execute(text("INSERT INTO public.profiles (id) VALUES (:u)"), {"u": str(user_id)})
        conn.execute(
            text("INSERT INTO public.morning_reports (user_id, report_date) VALUES (CAST(:u AS uuid), DATE '2026-10-12'), (CAST(:u AS uuid), DATE '2026-10-13')"),
            {"u": str(user_id)},
        )
    adapter = PostgresDeliveryAttempts(pg)
    attempt = DeliveryAttempt(user_id, date(2026, 10, 12), uuid4())
    assert adapter.claim(attempt) is not None
    assert adapter.finish_sent_with_legacy(attempt) is True
    with pg.connect() as conn:
        markers = conn.execute(
            text("SELECT report_date, kakao_sent_at IS NOT NULL FROM public.morning_reports WHERE user_id = CAST(:u AS uuid) ORDER BY report_date"),
            {"u": str(user_id)},
        ).all()
        assert markers == [(date(2026, 10, 12), True), (date(2026, 10, 13), False)]
    next_day = DeliveryAttempt(user_id, date(2026, 10, 13), uuid4())
    assert adapter.claim(next_day) is not None


def test_expired_sending_lease_never_allows_automatic_duplicate(pg):
    from datetime import date
    from services.kakao_delivery_postgres import DeliveryAttempt, PostgresDeliveryAttempts
    from services.kakao_delivery_staged import run_staged_delivery
    from services.kakao_delivery_orchestrator import SendOutcome

    user_id = uuid4()
    with pg.begin() as conn:
        conn.execute(text("INSERT INTO public.profiles (id) VALUES (:u)"), {"u": str(user_id)})
        conn.execute(text("INSERT INTO public.morning_reports (user_id, report_date) VALUES (CAST(:u AS uuid), DATE '2026-10-12')"), {"u": str(user_id)})
    attempt = DeliveryAttempt(user_id, date(2026, 10, 12), uuid4())
    adapter = PostgresDeliveryAttempts(pg)
    assert adapter.claim(attempt) is not None
    with pg.begin() as conn:
        conn.execute(
            text("UPDATE public.kakao_delivery_attempts SET lease_expires_at = now() - interval '1 hour' WHERE attempt_id = CAST(:id AS uuid)"),
            {"id": str(attempt.attempt_id)},
        )
    result = run_staged_delivery(
        engine=pg, user_id=user_id, report_date=date(2026, 10, 12),
        transport=lambda: pytest.fail("expired lease caused duplicate send"),
        env={"KAKAO_DELIVERY_STATE_ENABLED": "true", "KAKAO_DELIVERY_CUTOVER_APPROVED": "true"},
    )
    assert result.outcome == SendOutcome.NOT_CLAIMED
    with pg.connect() as conn:
        assert conn.execute(
            text("SELECT status FROM public.kakao_delivery_attempts WHERE attempt_id = CAST(:id AS uuid)"),
            {"id": str(attempt.attempt_id)},
        ).scalar_one() == "sending"


def test_staged_migration_can_be_reapplied_idempotently(pg):
    sql = Path("database/migrations/20261012_kakao_delivery_attempts.sql").read_text(encoding="utf-8")
    with pg.begin() as conn:
        conn.exec_driver_sql(sql)
        assert conn.execute(text("SELECT to_regclass('public.kakao_delivery_attempts') IS NOT NULL")).scalar_one() is True
        for role in ("anon", "authenticated"):
            assert conn.execute(
                text("SELECT has_function_privilege(:role, 'public.finish_kakao_delivery_with_legacy(uuid,uuid)', 'EXECUTE')"),
                {"role": role},
            ).scalar_one() is False


def test_staged_functions_are_security_invoker_and_not_publicly_executable(pg):
    signatures = [
        "public.claim_kakao_delivery_attempt(uuid,date,uuid,integer)",
        "public.finish_kakao_delivery_attempt(uuid,uuid,text,text)",
        "public.finish_kakao_delivery_with_legacy(uuid,uuid)",
    ]
    with pg.connect() as conn:
        for signature in signatures:
            assert conn.execute(
                text("SELECT prosecdef FROM pg_proc WHERE oid = CAST(:signature AS regprocedure)"),
                {"signature": signature},
            ).scalar_one() is False
            for role in ("anon", "authenticated"):
                assert conn.execute(
                    text("SELECT has_function_privilege(:role, CAST(:signature AS regprocedure), 'EXECUTE')"),
                    {"role": role, "signature": signature},
                ).scalar_one() is False


def test_client_roles_cannot_use_delivery_sequence_or_truncate_attempts(pg):
    with pg.connect() as conn:
        sequence = conn.execute(
            text("SELECT pg_get_serial_sequence('public.kakao_delivery_attempts', 'id')")
        ).scalar_one()
        assert sequence is not None
        for role in ("anon", "authenticated"):
            assert conn.execute(
                text("SELECT has_table_privilege(:role, 'public.kakao_delivery_attempts', 'DELETE')"),
                {"role": role},
            ).scalar_one() is False
            assert conn.execute(
                text("SELECT has_table_privilege(:role, 'public.kakao_delivery_attempts', 'TRUNCATE')"),
                {"role": role},
            ).scalar_one() is False
            assert conn.execute(
                text("SELECT has_sequence_privilege(:role, CAST(:seq AS regclass), 'USAGE')"),
                {"role": role, "seq": sequence},
            ).scalar_one() is False


def test_disposable_backend_owner_has_required_delivery_permissions(pg):
    # This checks the CI database owner only, NOT the actual Supabase service role.
    with pg.connect() as conn:
        assert conn.execute(text("SELECT has_schema_privilege(current_user, 'public', 'USAGE')")).scalar_one()
        for table, privilege in (
            ("public.morning_reports", "SELECT"),
            ("public.morning_reports", "UPDATE"),
            ("public.kakao_delivery_attempts", "SELECT"),
            ("public.kakao_delivery_attempts", "INSERT"),
            ("public.kakao_delivery_attempts", "UPDATE"),
        ):
            assert conn.execute(
                text("SELECT has_table_privilege(current_user, :table, :privilege)"),
                {"table": table, "privilege": privilege},
            ).scalar_one()
        for signature in (
            "public.claim_kakao_delivery_attempt(uuid,date,uuid,integer)",
            "public.finish_kakao_delivery_attempt(uuid,uuid,text,text)",
            "public.finish_kakao_delivery_with_legacy(uuid,uuid)",
        ):
            assert conn.execute(
                text("SELECT has_function_privilege(current_user, CAST(:signature AS regprocedure), 'EXECUTE')"),
                {"signature": signature},
            ).scalar_one()


def test_non_atomic_sent_completion_is_rejected_without_mutating_markers(pg):
    user_id, attempt_id = uuid4(), uuid4()
    with pg.begin() as conn:
        conn.execute(text("INSERT INTO public.profiles (id) VALUES (:id)"), {"id": str(user_id)})
        conn.execute(text("INSERT INTO public.morning_reports (user_id, report_date) VALUES (CAST(:u AS uuid), DATE '2026-10-12')"), {"u": str(user_id)})
        args = {"u": str(user_id), "a": str(attempt_id)}
        assert conn.execute(text("SELECT public.claim_kakao_delivery_attempt(CAST(:u AS uuid), DATE '2026-10-12', CAST(:a AS uuid), 300)"), args).scalar_one() is not None
        import pytest
        with pytest.raises(Exception, match="invalid completion argument"):
            with conn.begin_nested():
                conn.execute(text("SELECT public.finish_kakao_delivery_attempt(CAST(:u AS uuid), CAST(:a AS uuid), 'sent', NULL)"), args)
        assert conn.execute(text("SELECT status FROM public.kakao_delivery_attempts WHERE attempt_id = CAST(:a AS uuid)"), args).scalar_one() == "sending"
        assert conn.execute(text("SELECT kakao_sent_at FROM public.morning_reports WHERE user_id = CAST(:u AS uuid) AND report_date = DATE '2026-10-12'"), args).scalar_one() is None


def test_python_adapter_rejects_non_atomic_sent_before_database_call(pg):
    from datetime import date
    from services.kakao_delivery_postgres import DeliveryAttempt, PostgresDeliveryAttempts

    adapter = PostgresDeliveryAttempts(pg)
    attempt = DeliveryAttempt(uuid4(), date(2026, 10, 12), uuid4())
    with pytest.raises(ValueError, match="invalid delivery completion status"):
        adapter.finish(attempt, "sent")
    with pg.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM public.kakao_delivery_attempts")).scalar_one() == 0


def test_parallel_staged_delivery_invokes_mock_transport_once(pg):
    """Exercise the real PostgreSQL claim under simultaneous sender calls."""
    from datetime import date
    from threading import Barrier, Lock
    from services.kakao_delivery_staged import run_staged_delivery
    from services.kakao_delivery_orchestrator import SendOutcome

    user_id = uuid4()
    day = date(2026, 10, 12)
    with pg.begin() as conn:
        conn.execute(text("INSERT INTO public.profiles (id) VALUES (:u)"), {"u": str(user_id)})
        conn.execute(text("INSERT INTO public.morning_reports (user_id, report_date) VALUES (CAST(:u AS uuid), :day)"), {"u": str(user_id), "day": day})

    barrier = Barrier(4)
    lock = Lock()
    calls = []
    env = {"KAKAO_DELIVERY_STATE_ENABLED": "true", "KAKAO_DELIVERY_CUTOVER_APPROVED": "true"}

    def transport():
        with lock:
            calls.append("kakao")
        return (True, "mock accepted")

    def worker(_):
        barrier.wait(timeout=10)
        return run_staged_delivery(
            engine=pg, user_id=user_id, report_date=day, transport=transport, env=env,
        ).outcome

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(worker, range(4)))
    assert outcomes.count(SendOutcome.SENT) == 1
    assert outcomes.count(SendOutcome.NOT_CLAIMED) == 3
    assert calls == ["kakao"]


def test_concurrent_staged_gateways_invoke_mock_transport_only_once(pg):
    """Competing real PostgreSQL claims across entrypoints permit one transport."""
    from datetime import date
    from threading import Barrier, Lock
    from services.kakao_delivery_staged import run_staged_delivery
    from services.kakao_delivery_orchestrator import SendOutcome

    user_id = uuid4()
    with pg.begin() as conn:
        conn.execute(text("INSERT INTO public.profiles (id) VALUES (:u)"), {"u": str(user_id)})
        conn.execute(
            text("INSERT INTO public.morning_reports (user_id, report_date) "
                 "VALUES (CAST(:u AS uuid), DATE '2026-10-12')"),
            {"u": str(user_id)},
        )
    env = {"KAKAO_DELIVERY_STATE_ENABLED": "true", "KAKAO_DELIVERY_CUTOVER_APPROVED": "true"}
    barrier = Barrier(4)
    lock = Lock()
    transports = []

    def invoke(origin):
        barrier.wait(timeout=15)

        def mock_transport():
            with lock:
                transports.append(origin)
            return (True, "mock accepted")

        return run_staged_delivery(
            engine=pg, user_id=user_id, report_date=date(2026, 10, 12),
            transport=mock_transport, env=env,
        ).outcome

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(invoke, ("scheduled", "manual", "cli", "cached")))

    assert outcomes.count(SendOutcome.SENT) == 1
    assert outcomes.count(SendOutcome.NOT_CLAIMED) == 3
    assert len(transports) == 1
    with pg.connect() as conn:
        assert conn.execute(
            text("SELECT count(*) FROM public.kakao_delivery_attempts WHERE user_id = :u"),
            {"u": user_id},
        ).scalar_one() == 1
        assert conn.execute(
            text("SELECT kakao_sent_at IS NOT NULL FROM public.morning_reports WHERE user_id = :u"),
            {"u": user_id},
        ).scalar_one() is True
