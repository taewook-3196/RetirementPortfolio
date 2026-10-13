import datetime as dt
from zoneinfo import ZoneInfo

from scripts import run_morning_report_delivery_audit as cli

KST = ZoneInfo("Asia/Seoul")


def test_combined_audit_uses_both_readers_without_sending(monkeypatch):
    observed = []
    monkeypatch.setattr(cli, "fetch_runs", lambda repository, token: observed.append(("github", repository)) or [
        {"id": 1, "event": "schedule", "created_at": "2026-10-12T22:10:00Z", "status": "completed", "conclusion": "success"}
    ])
    import scripts.morning_report_delivery_reader as reader
    monkeypatch.setattr(reader, "read_recipient_markers", lambda day: observed.append(("db", day)) or [
        {"enabled": True, "kakao_enabled": True, "report_date_marker_present": True}
    ])
    result = cli.run_audit(dt.date(2026, 10, 13), dt.datetime(2026, 10, 13, 10, tzinfo=KST), "owner/repo")
    assert observed == [("github", "owner/repo"), ("db", dt.date(2026, 10, 13))]
    assert result["missing_marker_count"] == 0
    assert result["diagnosis"] == "no_missing_delivery_markers"
    assert "user_id" not in str(result)


def test_audit_unavailable_does_not_claim_success(monkeypatch, capsys):
    monkeypatch.setattr(cli, "run_audit", lambda *args: (_ for _ in ()).throw(RuntimeError("sensitive details")))
    assert cli.main(["--date", "2026-10-13"]) == 2
    captured = capsys.readouterr().out
    assert "audit_unavailable" in captured
    assert "sensitive details" not in captured


def test_missing_markers_return_nonzero(monkeypatch):
    monkeypatch.setattr(cli, "run_audit", lambda *args: {
        "diagnosis": "delivery_marker_missing", "missing_marker_count": 1,
        "scheduled_run_diagnosis": "scheduled_run_succeeded_delivery_unverified"
    })
    assert cli.main(["--date", "2026-10-13"]) == 1


def test_zero_eligible_recipients_returns_nonzero(monkeypatch):
    monkeypatch.setattr(cli, "run_audit", lambda *args: {
        "diagnosis": "no_eligible_recipients_verify_configuration",
        "missing_marker_count": 0,
        "scheduled_run_diagnosis": "scheduled_run_succeeded_delivery_unverified",
    })
    assert cli.main(["--date", "2026-10-13"]) == 1


def test_failed_schedule_even_with_markers_requires_review(monkeypatch):
    monkeypatch.setattr(cli, "run_audit", lambda *args: {
        "diagnosis": "no_missing_delivery_markers",
        "missing_marker_count": 0,
        "scheduled_run_diagnosis": "scheduled_runs_completed_without_success",
    })
    assert cli.main(["--date", "2026-10-13"]) == 1


def test_running_schedule_requires_review_after_cutoff(monkeypatch):
    monkeypatch.setattr(cli, "run_audit", lambda *args: {
        "diagnosis": "no_missing_delivery_markers",
        "missing_marker_count": 0,
        "scheduled_run_diagnosis": "scheduled_run_in_progress",
    })
    assert cli.main(["--date", "2026-10-13"]) == 1
