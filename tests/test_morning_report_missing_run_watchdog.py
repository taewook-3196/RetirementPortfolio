"""Regression checks for the independent Morning Report missing-run watchdog."""

from pathlib import Path

WATCHDOG = (
    Path(__file__).resolve().parents[1]
    / ".github/workflows/morning_report_missing_run_watchdog.yml"
)


def test_watchdog_schedule_and_target():
    source = WATCHDOG.read_text(encoding="utf-8")
    assert "cron: '30 2 * * 2-6'" in source
    assert "workflow_id: 'morning_report.yml'" in source
    assert "timeZone: 'Asia/Seoul'" in source
    assert "11 * 60 + 30" in source
    assert "run.event === 'schedule'" in source


def test_watchdog_does_not_resend_or_access_secrets():
    source = WATCHDOG.read_text(encoding="utf-8")
    assert "  actions: read" in source
    assert "  issues: write" in source
    assert "secrets." not in source
    assert "DATABASE_URL" not in source
    assert "KAKAO_ACCESS_TOKEN" not in source
    assert "workflow_dispatch:" in source
    assert "createWorkflowDispatch" not in source


def test_watchdog_issue_lifecycle():
    source = WATCHDOG.read_text(encoding="utf-8")
    assert "missing-report-date:" in source
    assert "github.rest.issues.create" in source
    assert "github.rest.issues.update" in source
    assert "state: 'closed'" in source
    assert "Missing-run alert already exists for today" in source
