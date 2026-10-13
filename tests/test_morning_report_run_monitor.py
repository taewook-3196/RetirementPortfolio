"""Static safety checks for the independent Morning Report run monitor."""

from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/morning_report_run_monitor.yml"


def test_monitor_observes_existing_report_workflow():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_run:" in text
    assert '"Morning Portfolio Report & KakaoTalk Notification"' in text
    assert "      - completed" in text


def test_monitor_has_minimal_permissions_and_no_report_secrets():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "  actions: read" in text
    assert "  issues: write" in text
    assert "contents: write" not in text
    assert "secrets." not in text
    assert "DATABASE_URL" not in text
    assert "KAKAO_ACCESS_TOKEN" not in text
    assert "GEMINI_API_KEY" not in text


def test_monitor_ignores_stale_runs_and_duplicate_failures():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "listWorkflowRuns" in text
    assert "Number(other.run_number) > Number(run.run_number)" in text
    assert "runNumber < priorNumber" in text
    assert "priorNumber === runNumber" in text
    assert "state: 'closed'" in text
    assert "cancel-in-progress: false" in text
