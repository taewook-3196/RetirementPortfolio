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
