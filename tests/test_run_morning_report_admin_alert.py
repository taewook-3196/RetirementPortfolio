from scripts import run_morning_report_admin_alert as cli


def fake_audit(day, now, repository):
    return {
        "date_kst": day.isoformat(),
        "diagnosis": "delivery_marker_missing",
        "scheduled_run_diagnosis": "no_scheduled_runs",
    }


def test_default_is_dry_run_without_webhook(monkeypatch, capsys):
    monkeypatch.setattr(cli, "run_audit", fake_audit)
    monkeypatch.setattr(cli, "send_admin_webhook", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("sent")))
    assert cli.main(["--date", "2026-10-13"]) == 0
    assert '"mode": "dry_run"' in capsys.readouterr().out


def test_send_requires_explicit_configuration(monkeypatch, capsys):
    monkeypatch.setattr(cli, "run_audit", fake_audit)
    monkeypatch.delenv("MORNING_REPORT_ADMIN_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("MORNING_REPORT_ALERT_STORE_DIR", raising=False)
    assert cli.main(["--send", "--date", "2026-10-13"]) == 2
    assert "webhook" not in capsys.readouterr().out.lower()


def test_explicit_send_uses_runner(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "run_audit", fake_audit)
    monkeypatch.setenv("MORNING_REPORT_ADMIN_WEBHOOK_URL", "https://alerts.example.com/hook")
    monkeypatch.setenv("MORNING_REPORT_ALERT_STORE_DIR", str(tmp_path))
    sent = []
    monkeypatch.setattr(cli, "send_admin_webhook", lambda message, url: sent.append((message, url)))
    assert cli.main(["--send", "--date", "2026-10-13"]) == 0
    assert len(sent) == 1
    assert cli.main(["--send", "--date", "2026-10-13"]) == 0
    assert len(sent) == 1
