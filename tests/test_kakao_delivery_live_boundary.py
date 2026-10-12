"""Regression guard: no staged Kakao sender is wired alongside legacy transport.

This is intentionally a source-level inventory, not proof of production readiness.
When a reviewed cutover is implemented, replace these checks with end-to-end
entrypoint tests and remove the legacy-only assumptions.
"""
from pathlib import Path


def test_daily_report_inventories_both_legacy_kakao_transport_paths():
    source = Path("services/daily_report_service.py").read_text(encoding="utf-8")
    assert source.count("self.kakao_service.send_morning_report(summary_text, report_web_url)") == 2
    assert source.count("self.repo.mark_morning_report_kakao_sent(report_date)") == 1


def test_staged_transport_not_imported_into_live_entrypoints():
    for path in (
        "services/daily_report_service.py",
        "scripts/run_multi_user_morning_reports.py",
        "ui/settings_page.py",
    ):
        source = Path(path).read_text(encoding="utf-8")
        assert "kakao_delivery_transport_adapter" not in source
        assert "send_staged_morning_report" not in source
        assert "run_staged_delivery" not in source
