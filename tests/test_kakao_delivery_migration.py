"""Static safeguards for the staged Kakao delivery migration."""
from pathlib import Path


def test_attempt_migration_is_private_and_has_active_uniqueness():
    sql = Path("database/migrations/20261012_kakao_delivery_attempts.sql").read_text(encoding="utf-8")
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "REVOKE ALL ON TABLE public.kakao_delivery_attempts FROM anon, authenticated" in sql
    assert "kakao_delivery_attempts_one_active_per_day" in sql
    assert "WHERE status IN ('pending', 'sending', 'sent', 'uncertain')" in sql
    assert "REFERENCES public.profiles(id) ON DELETE CASCADE" in sql


def test_migration_is_not_executed_by_morning_report_workflow():
    workflow = Path(".github/workflows/morning_report.yml").read_text(encoding="utf-8")
    assert "20261012_kakao_delivery_attempts.sql" not in workflow


def test_claim_requires_successful_insert_and_restricts_execution():
    sql = Path("database/migrations/20261012_kakao_delivery_attempts.sql").read_text(encoding="utf-8")
    assert "CREATE OR REPLACE FUNCTION public.claim_kakao_delivery_attempt(" in sql
    assert "ON CONFLICT DO NOTHING" in sql
    assert "RETURNING id INTO v_id" in sql
    assert "REVOKE ALL ON FUNCTION public.claim_kakao_delivery_attempt" in sql
    assert "FROM PUBLIC, anon, authenticated" in sql
    assert "SECURITY INVOKER" in sql


def test_completion_requires_attempt_ownership_and_nonterminal_state():
    sql = Path("database/migrations/20261012_kakao_delivery_attempts.sql").read_text(encoding="utf-8")
    finish = sql.split("CREATE OR REPLACE FUNCTION public.finish_kakao_delivery_attempt(", 1)[1]
    assert "AND attempt_id = p_attempt_id" in finish
    assert "AND status = 'sending'" in finish
    assert "p_final_status NOT IN ('sent', 'uncertain', 'failed_before_send')" in finish
    assert "RETURN v_id IS NOT NULL" in finish
    assert "REVOKE ALL ON FUNCTION public.finish_kakao_delivery_attempt" in finish
