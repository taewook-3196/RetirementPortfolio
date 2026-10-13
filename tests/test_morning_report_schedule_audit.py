import datetime as dt

from scripts.audit_morning_report_schedule import audit_runs, expected_slots


def test_expected_schedule_only_tuesday_through_saturday():
    assert expected_slots(dt.date(2026, 10, 13)) == ("05:35", "07:10", "09:00")
    assert expected_slots(dt.date(2026, 10, 12)) == ()
    assert expected_slots(dt.date(2026, 10, 11)) == ()


def test_manual_success_does_not_hide_missing_schedule():
    result = audit_runs(dt.date(2026, 10, 13), [
        {"id": 1, "event": "workflow_dispatch", "created_at": "2026-10-13T00:25:00Z", "conclusion": "success"}
    ])
    assert result["schedule_missing"] is True
    assert len(result["manual_runs"]) == 1
    assert result["scheduled_runs"] == []


def test_scheduled_run_counts_even_if_failed():
    result = audit_runs(dt.date(2026, 10, 13), [
        {"id": 2, "event": "schedule", "created_at": "2026-10-12T20:36:00Z", "conclusion": "failure"}
    ])
    assert result["schedule_missing"] is False
    assert result["scheduled_runs"][0]["conclusion"] == "failure"


def test_utc_boundary_and_other_days_are_filtered():
    result = audit_runs(dt.date(2026, 10, 13), [
        {"id": 3, "event": "schedule", "created_at": "2026-10-12T14:59:00Z"},
        {"id": 4, "event": "schedule", "created_at": "2026-10-12T15:01:00Z"},
    ])
    assert [r["id"] for r in result["scheduled_runs"]] == [4]


def test_no_alert_on_non_schedule_days():
    assert audit_runs(dt.date(2026, 10, 12), [])["schedule_missing"] is False


def test_failed_scheduled_runs_have_distinct_diagnosis():
    result = audit_runs(dt.date(2026, 10, 13), [
        {"id": 9, "event": "schedule", "created_at": "2026-10-12T20:35:00Z", "status": "completed", "conclusion": "failure"}
    ])
    assert result["diagnosis"] == "scheduled_runs_completed_without_success"
    assert result["schedule_missing"] is False


def test_successful_schedule_does_not_claim_kakao_was_delivered():
    result = audit_runs(dt.date(2026, 10, 13), [
        {"id": 10, "event": "schedule", "created_at": "2026-10-12T20:35:00Z", "status": "completed", "conclusion": "success"}
    ])
    assert result["diagnosis"] == "scheduled_run_succeeded_delivery_unverified"


def test_running_schedule_is_not_reported_as_failed():
    result = audit_runs(dt.date(2026, 10, 13), [
        {"id": 11, "event": "schedule", "created_at": "2026-10-12T20:35:00Z", "status": "in_progress", "conclusion": None}
    ])
    assert result["diagnosis"] == "scheduled_run_in_progress"


def test_successful_run_takes_priority_over_other_running_attempt():
    result = audit_runs(dt.date(2026, 10, 13), [
        {"id": 12, "event": "schedule", "created_at": "2026-10-12T20:35:00Z", "status": "completed", "conclusion": "success"},
        {"id": 13, "event": "schedule", "created_at": "2026-10-12T22:10:00Z", "status": "queued", "conclusion": None},
    ])
    assert result["diagnosis"] == "scheduled_run_succeeded_delivery_unverified"


def test_github_query_uses_exact_kst_calendar_day(monkeypatch):
    import io
    import json
    from scripts import audit_morning_report_schedule as audit

    seen = []

    class Response:
        def __enter__(self):
            return io.BytesIO(json.dumps({"total_count": 0, "workflow_runs": []}).encode())

        def __exit__(self, *args):
            return False

    def fake_urlopen(request, timeout):
        seen.append(request.full_url)
        return Response()

    monkeypatch.setattr(audit.urllib.request, "urlopen", fake_urlopen)
    audit.fetch_runs("owner/repo", day=dt.date(2026, 10, 13))
    from urllib.parse import parse_qs, urlsplit
    params = parse_qs(urlsplit(seen[0]).query)
    assert params["created"] == ["2026-10-12T15:00:00Z..2026-10-13T15:00:00Z"]


def test_truncated_github_results_raise_instead_of_claiming_no_runs(monkeypatch):
    import io
    import json
    import pytest
    from scripts import audit_morning_report_schedule as audit

    class Response:
        def __enter__(self):
            return io.BytesIO(json.dumps({"total_count": 101, "workflow_runs": []}).encode())

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(audit.urllib.request, "urlopen", lambda request, timeout: Response())
    with pytest.raises(ValueError, match="capacity"):
        audit.fetch_runs("owner/repo", day=dt.date(2026, 10, 13))
