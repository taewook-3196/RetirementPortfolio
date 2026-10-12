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


def test_report_service_does_not_log_sensitive_delivery_exceptions():
    source = Path("services/daily_report_service.py").read_text(encoding="utf-8")
    assert 'logger.exception("모닝 리포트 생성 및 발송 실패")' not in source
    assert '"다음 스케줄에서 중복 발송될 수 있습니다. user_id=%s error=%s"' not in source
    assert 'type(last_record_error).__name__' in source


def test_ambiguous_kakao_delivery_record_is_reconciled_by_readback():
    source = Path("services/daily_report_service.py").read_text(encoding="utf-8")
    assert "persisted = self.repo.get_morning_report_for_date(report_date)" in source
    assert 'getattr(persisted, "kakao_sent_at", None) is not None' in source
    assert source.index("persisted = self.repo.get_morning_report_for_date(report_date)") < source.index('"다음 스케줄에서 중복 발송될 수 있습니다. error_type=%s"')
