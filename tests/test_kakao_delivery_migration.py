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
    assert "p_final_status NOT IN ('uncertain', 'failed_before_send')" in finish
    assert "RETURN v_id IS NOT NULL" in finish
    assert "REVOKE ALL ON FUNCTION public.finish_kakao_delivery_attempt" in finish


def test_staged_migration_matches_morning_report_model_contract():
    from database.models import MorningReport
    from sqlalchemy import UniqueConstraint

    columns = MorningReport.__table__.columns
    assert {"user_id", "report_date", "kakao_sent_at", "updated_at"}.issubset(columns.keys())
    assert columns["kakao_sent_at"].nullable
    assert columns["user_id"].type.as_generic().__class__.__name__ == "Uuid"
    assert any(
        isinstance(constraint, UniqueConstraint)
        and set(constraint.columns.keys()) == {"user_id", "report_date"}
        for constraint in MorningReport.__table__.constraints
    )
    sql = Path("database/migrations/20261012_kakao_delivery_attempts.sql").read_text(encoding="utf-8")
    assert "FROM public.morning_reports" in sql
    assert "kakao_sent_at IS NOT NULL" in sql
    assert "SET kakao_sent_at = COALESCE(kakao_sent_at, now()), updated_at = now()" in sql


def test_current_scheduled_manual_cli_entrypoints_share_report_service():
    """Inventory guard: review integration if a send entrypoint changes."""
    scheduled = Path("scripts/run_multi_user_morning_reports.py").read_text(encoding="utf-8")
    manual = Path("ui/settings_page.py").read_text(encoding="utf-8")
    service = Path("services/daily_report_service.py").read_text(encoding="utf-8")
    assert "service.generate_and_send(" in scheduled
    assert "force_kakao=send_kakao" in scheduled
    assert "service.generate_and_send(send_kakao=True, force_kakao=True)" in manual
    assert "def run_daily_report_cli():" in service
    assert "service.generate_and_send(send_kakao=not generate_only, force_kakao=not generate_only)" in service
    assert "self.kakao_service.send_morning_report(summary_text, report_web_url)" in service
    assert "self.repo.mark_morning_report_kakao_sent(report_date)" in service
