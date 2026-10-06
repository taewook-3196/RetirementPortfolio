"""Task 13 scheduler behavior tests."""

from datetime import datetime, time
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

import scripts.run_multi_user_morning_reports as runner

SEOUL = ZoneInfo("Asia/Seoul")


def test_is_due_respects_user_time():
    settings = SimpleNamespace(morning_report_enabled=True, morning_report_time=time(7, 30))
    assert runner._is_due(settings, datetime(2026, 10, 2, 7, 29, tzinfo=SEOUL)) is False
    assert runner._is_due(settings, datetime(2026, 10, 2, 7, 30, tzinfo=SEOUL)) is True


def test_one_user_failure_does_not_stop_next_user(monkeypatch):
    first, second = uuid4(), uuid4()
    calls = []

    class FakeRepo:
        def __init__(self, user_id):
            self.user_id = user_id
        @staticmethod
        def get_morning_report_user_ids():
            return [first, second]
        def get_user_settings(self):
            if self.user_id == first:
                raise RuntimeError("boom")
            return SimpleNamespace(
                morning_report_enabled=True,
                morning_report_time=time(7, 0),
                kakao_enabled=False,
            )
        def get_morning_report_for_date(self, report_date):
            return None

    class FakeService:
        def __init__(self, config, repo):
            self.repo = repo
        def generate_and_send(self, **kwargs):
            calls.append(self.repo.user_id)
            return True, "ok", None

    monkeypatch.setattr(runner, "init_db", lambda: None)
    monkeypatch.setattr(runner, "load_config", lambda: object())
    monkeypatch.setattr(runner, "Repository", FakeRepo)
    monkeypatch.setattr(runner, "DailyReportService", FakeService)

    result = runner.run_all_users(datetime(2026, 10, 2, 8, 0, tzinfo=SEOUL))
    assert result == 1
    assert calls == [second]


def test_existing_report_skips_duplicate_send(monkeypatch):
    user_id = uuid4()
    calls = []

    class FakeRepo:
        def __init__(self, user_id):
            self.user_id = user_id
        @staticmethod
        def get_morning_report_user_ids():
            return [user_id]
        def get_user_settings(self):
            return SimpleNamespace(
                morning_report_enabled=True,
                morning_report_time=time(7, 0),
                kakao_enabled=True,
            )
        def get_morning_report_for_date(self, report_date):
            return SimpleNamespace(kakao_sent_at=datetime(2026, 10, 2, 7, 5, tzinfo=SEOUL))

    class FakeService:
        def __init__(self, config, repo):
            calls.append(repo.user_id)

    monkeypatch.setattr(runner, "init_db", lambda: None)
    monkeypatch.setattr(runner, "load_config", lambda: object())
    monkeypatch.setattr(runner, "Repository", FakeRepo)
    monkeypatch.setattr(runner, "DailyReportService", FakeService)

    assert runner.run_all_users(datetime(2026, 10, 2, 8, 0, tzinfo=SEOUL)) == 0
    assert calls == []


def test_unsent_kakao_report_is_retried(monkeypatch):
    user_id = uuid4()
    calls = []

    class FakeRepo:
        def __init__(self, user_id):
            self.user_id = user_id
        @staticmethod
        def get_morning_report_user_ids():
            return [user_id]
        def get_user_settings(self):
            return SimpleNamespace(
                morning_report_enabled=True,
                morning_report_time=time(7, 0),
                kakao_enabled=True,
            )
        def get_morning_report_for_date(self, report_date):
            return SimpleNamespace(kakao_sent_at=None)

    class FakeService:
        def __init__(self, config, repo):
            self.repo = repo
        def generate_and_send(self, **kwargs):
            calls.append(self.repo.user_id)
            return True, "ok", None

    monkeypatch.setattr(runner, "init_db", lambda: None)
    monkeypatch.setattr(runner, "load_config", lambda: object())
    monkeypatch.setattr(runner, "Repository", FakeRepo)
    monkeypatch.setattr(runner, "DailyReportService", FakeService)

    assert runner.run_all_users(datetime(2026, 10, 2, 8, 0, tzinfo=SEOUL)) == 0
    assert calls == [user_id]


def test_force_resend_bypasses_existing_sent_report(monkeypatch):
    user_id = uuid4()
    calls = []

    class FakeRepo:
        def __init__(self, user_id):
            self.user_id = user_id
        @staticmethod
        def get_morning_report_user_ids():
            return [user_id]
        def get_user_settings(self):
            return SimpleNamespace(
                morning_report_enabled=True,
                morning_report_time=time(7, 0),
                kakao_enabled=True,
            )
        def get_morning_report_for_date(self, report_date):
            return SimpleNamespace(kakao_sent_at=datetime(2026, 10, 2, 7, 5, tzinfo=SEOUL))

    class FakeService:
        def __init__(self, config, repo):
            self.repo = repo
        def generate_and_send(self, **kwargs):
            calls.append((self.repo.user_id, kwargs))
            return True, "ok", None

    monkeypatch.setattr(runner, "init_db", lambda: None)
    monkeypatch.setattr(runner, "load_config", lambda: object())
    monkeypatch.setattr(runner, "Repository", FakeRepo)
    monkeypatch.setattr(runner, "DailyReportService", FakeService)

    assert runner.run_all_users(
        datetime(2026, 10, 2, 8, 0, tzinfo=SEOUL), force=True
    ) == 0
    assert calls and calls[0][0] == user_id



def test_force_resend_bypasses_scheduled_time(monkeypatch):
    user_id = uuid4()
    calls = []

    class FakeRepo:
        def __init__(self, user_id):
            self.user_id = user_id
        @staticmethod
        def get_morning_report_user_ids():
            return [user_id]
        def get_user_settings(self):
            return SimpleNamespace(
                morning_report_enabled=True,
                morning_report_time=time(7, 0),
                kakao_enabled=True,
            )
        def get_morning_report_for_date(self, report_date):
            return None

    class FakeService:
        def __init__(self, config, repo):
            self.repo = repo
        def generate_and_send(self, **kwargs):
            calls.append((self.repo.user_id, kwargs))
            return True, "ok", None

    monkeypatch.setattr(runner, "init_db", lambda: None)
    monkeypatch.setattr(runner, "load_config", lambda: object())
    monkeypatch.setattr(runner, "Repository", FakeRepo)
    monkeypatch.setattr(runner, "DailyReportService", FakeService)

    assert runner.run_all_users(
        datetime(2026, 10, 2, 6, 0, tzinfo=SEOUL), force=True
    ) == 0
    assert calls and calls[0][0] == user_id
    assert calls[0][1]["force_kakao"] is True
