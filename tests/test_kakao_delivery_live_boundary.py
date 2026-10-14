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


def test_live_entrypoints_cannot_activate_staged_sender_via_environment_only():
    """Both opt-in flags alone must not enable a parallel production sender."""
    live_paths = (
        "services/daily_report_service.py",
        "scripts/run_multi_user_morning_reports.py",
        "ui/settings_page.py",
    )
    forbidden = (
        "kakao_delivery_staged",
        "kakao_delivery_orchestrator",
        "kakao_delivery_postgres",
        "KAKAO_DELIVERY_STATE_ENABLED",
        "KAKAO_DELIVERY_CUTOVER_APPROVED",
    )
    for path in live_paths:
        source = Path(path).read_text(encoding="utf-8")
        for marker in forbidden:
            assert marker not in source, f"{path} unexpectedly references staged delivery marker {marker}"


def test_staged_modules_do_not_import_live_report_sender():
    """Staged modules must not start the legacy sender as a side effect."""
    for path in Path("services").glob("kakao_delivery_*.py"):
        source = path.read_text(encoding="utf-8")
        assert "from services.daily_report_service import" not in source
        assert "import services.daily_report_service" not in source
        assert "from scripts.run_multi_user_morning_reports import" not in source


def test_live_boundary_inventory_is_explicit_about_manual_and_scheduled_paths():
    """Keep an auditable inventory so a new caller cannot be overlooked."""
    entrypoints = {
        "scheduled": Path("scripts/run_multi_user_morning_reports.py"),
        "report_service": Path("services/daily_report_service.py"),
        "settings": Path("ui/settings_page.py"),
    }
    for name, path in entrypoints.items():
        assert path.is_file(), f"missing {name} entrypoint: {path}"
        source = path.read_text(encoding="utf-8")
        assert "run_staged_delivery(" not in source
        assert "send_with_delivery_claim(" not in source


def test_cached_kakao_sender_is_tracked_as_separate_cutover_path():
    """The cached-payload path also sends Kakao and must not be missed at cutover."""
    source = Path("services/daily_report_service.py").read_text(encoding="utf-8")
    cached = source.split("    def send_cached_kakao(", 1)
    assert len(cached) == 2, "cached Kakao entrypoint was moved or removed"
    body = cached[1].split("def run_daily_report_cli(", 1)[0]
    assert "self.kakao_service.send_morning_report(" in body
    assert "run_staged_delivery(" not in body


def test_cutover_acceptance_document_tracks_cached_sender():
    document = Path("docs/kakao_delivery_cutover_acceptance.md").read_text(encoding="utf-8")
    assert "send_cached_kakao" in document
