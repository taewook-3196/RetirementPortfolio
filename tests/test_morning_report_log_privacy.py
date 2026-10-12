"""Regression checks for public scheduled-report log privacy."""
from pathlib import Path


def test_scheduler_does_not_emit_raw_user_ids_or_tracebacks():
    source = Path("scripts/run_multi_user_morning_reports.py").read_text(encoding="utf-8")
    assert "logger.exception(" not in source
    assert 'logger.info("사용자별 모닝 리포트 완료: %s", user_id)' not in source
    assert 'logger.error("사용자별 모닝 리포트 실패: %s / %s", user_id, message)' not in source


def test_scheduled_workflow_uses_read_only_token():
    workflow = Path(".github/workflows/morning_report.yml").read_text(encoding="utf-8")
    assert "contents: read" in workflow
    assert "pull_request_target:" not in workflow
