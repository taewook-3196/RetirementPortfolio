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
        def get_kakao_credential(self):
            return SimpleNamespace(scopes="talk_message")

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
        def get_kakao_credential(self):
            return SimpleNamespace(scopes="talk_message")

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
        def get_kakao_credential(self):
            return SimpleNamespace(scopes="talk_message")

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
        def get_kakao_credential(self):
            return SimpleNamespace(scopes="talk_message")

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
        def get_kakao_credential(self):
            return SimpleNamespace(scopes="talk_message")

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



def test_due_users_share_one_market_price_sync(monkeypatch):
    first, second = uuid4(), uuid4()
    sync_calls = []
    report_calls = []

    class FakeRepo:
        def __init__(self, user_id):
            self.user_id = user_id
        @staticmethod
        def get_morning_report_user_ids():
            return [first, second]
        def get_user_settings(self):
            return SimpleNamespace(
                morning_report_enabled=True,
                morning_report_time=time(7, 0),
                kakao_enabled=False,
            )
        def get_kakao_credential(self):
            return SimpleNamespace(scopes="talk_message")

        def get_morning_report_for_date(self, report_date):
            return None
        def get_account_targets(self, account_id=None):
            return [SimpleNamespace(ticker=str(self.user_id), name="target")]
        def get_transactions(self):
            return []
        def get_etf_master(self, ticker):
            return None
        def save_etf_master(self, items):
            return len(items)
        def upsert_prices(self, items):
            return len(items)

    class FakeService:
        def __init__(self, config, repo):
            self.repo = repo
        def generate_and_send(self, **kwargs):
            report_calls.append((self.repo.user_id, kwargs))
            return True, "ok", None

    def fake_update_market_prices(**kwargs):
        repo = kwargs["repo"]
        sync_calls.append([item.ticker for item in repo.get_account_targets()])
        return {"saved": 0}

    monkeypatch.setattr(runner, "init_db", lambda: None)
    monkeypatch.setattr(runner, "load_config", lambda: object())
    monkeypatch.setattr(runner, "Repository", FakeRepo)
    monkeypatch.setattr(runner, "DailyReportService", FakeService)
    monkeypatch.setattr(runner, "update_market_prices", fake_update_market_prices)

    assert runner.run_all_users(
        datetime(2026, 10, 2, 8, 0, tzinfo=SEOUL)
    ) == 0
    assert sync_calls == [[str(first), str(second)]]
    assert [user_id for user_id, _ in report_calls] == [first, second]
    assert all(kwargs["update_prices"] is False for _, kwargs in report_calls)



def test_multi_user_delivery_states_are_isolated(monkeypatch):
    no_kakao, retry_kakao, already_sent = uuid4(), uuid4(), uuid4()
    calls = []
    existing = {
        no_kakao: None,
        retry_kakao: SimpleNamespace(kakao_sent_at=None),
        already_sent: SimpleNamespace(
            kakao_sent_at=datetime(2026, 10, 2, 7, 5, tzinfo=SEOUL)
        ),
    }

    class FakeRepo:
        def __init__(self, user_id):
            self.user_id = user_id

        @staticmethod
        def get_morning_report_user_ids():
            return [no_kakao, retry_kakao, already_sent]

        def get_user_settings(self):
            return SimpleNamespace(
                morning_report_enabled=True,
                morning_report_time=time(7, 0),
                kakao_enabled=self.user_id != no_kakao,
            )

        def get_kakao_credential(self):
            return SimpleNamespace(scopes="talk_message")

        def get_morning_report_for_date(self, report_date):
            return existing[self.user_id]

        def get_account_targets(self, account_id=None):
            return []

        def get_transactions(self):
            return []

        def get_etf_master(self, ticker):
            return None

        def save_etf_master(self, items):
            return len(items)

        def upsert_prices(self, items):
            return len(items)

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
    monkeypatch.setattr(runner, "update_market_prices", lambda **kwargs: {"saved": 0})

    assert runner.run_all_users(
        datetime(2026, 10, 2, 8, 0, tzinfo=SEOUL)
    ) == 0

    assert [user_id for user_id, _ in calls] == [no_kakao, retry_kakao]
    assert calls[0][1]["send_kakao"] is False
    assert calls[0][1]["force_kakao"] is False
    assert calls[1][1]["send_kakao"] is True
    assert calls[1][1]["force_kakao"] is True


def test_one_kakao_delivery_failure_does_not_block_other_user(monkeypatch):
    failing, succeeding = uuid4(), uuid4()
    calls = []

    class FakeRepo:
        def __init__(self, user_id):
            self.user_id = user_id

        @staticmethod
        def get_morning_report_user_ids():
            return [failing, succeeding]

        def get_user_settings(self):
            return SimpleNamespace(
                morning_report_enabled=True,
                morning_report_time=time(7, 0),
                kakao_enabled=True,
            )

        def get_kakao_credential(self):
            return SimpleNamespace(scopes="talk_message")

        def get_morning_report_for_date(self, report_date):
            return None

        def get_account_targets(self, account_id=None):
            return []

        def get_transactions(self):
            return []

        def get_etf_master(self, ticker):
            return None

        def save_etf_master(self, items):
            return len(items)

        def upsert_prices(self, items):
            return len(items)

    class FakeService:
        def __init__(self, config, repo):
            self.repo = repo

        def generate_and_send(self, **kwargs):
            calls.append(self.repo.user_id)
            if self.repo.user_id == failing:
                return False, "kakao failed", None
            return True, "ok", None

    monkeypatch.setattr(runner, "init_db", lambda: None)
    monkeypatch.setattr(runner, "load_config", lambda: object())
    monkeypatch.setattr(runner, "Repository", FakeRepo)
    monkeypatch.setattr(runner, "DailyReportService", FakeService)
    monkeypatch.setattr(runner, "update_market_prices", lambda **kwargs: {"saved": 0})

    assert runner.run_all_users(
        datetime(2026, 10, 2, 8, 0, tzinfo=SEOUL)
    ) == 1
    assert calls == [failing, succeeding]



def test_missing_kakao_scope_generates_report_without_delivery(monkeypatch):
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

        def get_kakao_credential(self):
            return SimpleNamespace(scopes="")

        def get_morning_report_for_date(self, report_date):
            return None

        def get_account_targets(self, account_id=None):
            return []

        def get_transactions(self):
            return []

        def get_etf_master(self, ticker):
            return None

        def save_etf_master(self, items):
            return len(items)

        def upsert_prices(self, items):
            return len(items)

    class FakeService:
        def __init__(self, config, repo):
            self.repo = repo

        def generate_and_send(self, **kwargs):
            calls.append(kwargs)
            return True, "ok", None

    monkeypatch.setattr(runner, "init_db", lambda: None)
    monkeypatch.setattr(runner, "load_config", lambda: object())
    monkeypatch.setattr(runner, "Repository", FakeRepo)
    monkeypatch.setattr(runner, "DailyReportService", FakeService)
    monkeypatch.setattr(runner, "update_market_prices", lambda **kwargs: {"saved": 0})

    assert runner.run_all_users(
        datetime(2026, 10, 2, 8, 0, tzinfo=SEOUL)
    ) == 0
    assert len(calls) == 1
    assert calls[0]["send_kakao"] is False
    assert calls[0]["force_kakao"] is False


def test_existing_unsent_report_without_kakao_scope_is_not_reprocessed(monkeypatch):
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

        def get_kakao_credential(self):
            return SimpleNamespace(scopes="")

        def get_morning_report_for_date(self, report_date):
            return SimpleNamespace(kakao_sent_at=None)

        def get_account_targets(self, account_id=None):
            return []

        def get_transactions(self):
            return []

        def get_etf_master(self, ticker):
            return None

        def save_etf_master(self, items):
            return len(items)

        def upsert_prices(self, items):
            return len(items)

    class FakeService:
        def __init__(self, config, repo):
            calls.append(repo.user_id)

    monkeypatch.setattr(runner, "init_db", lambda: None)
    monkeypatch.setattr(runner, "load_config", lambda: object())
    monkeypatch.setattr(runner, "Repository", FakeRepo)
    monkeypatch.setattr(runner, "DailyReportService", FakeService)
    monkeypatch.setattr(runner, "update_market_prices", lambda **kwargs: {"saved": 0})

    assert runner.run_all_users(
        datetime(2026, 10, 2, 8, 0, tzinfo=SEOUL)
    ) == 0
    assert calls == []


def test_price_sync_warning_still_generates_due_report(monkeypatch, caplog):
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
                kakao_enabled=False,
            )
        def get_morning_report_for_date(self, report_date):
            return None
        def get_account_targets(self, account_id=None):
            return []
        def get_transactions(self):
            return []
        def get_etf_master(self, ticker):
            return None
        def save_etf_master(self, items):
            return len(items)
        def upsert_prices(self, items):
            return len(items)

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
    monkeypatch.setattr(
        runner,
        "update_market_prices",
        lambda **kwargs: {
            "status": "warning",
            "saved_count": 0,
            "message": "no fresh prices",
        },
    )

    assert runner.run_all_users(
        datetime(2026, 10, 2, 8, 0, tzinfo=SEOUL)
    ) == 0
    assert calls == [user_id]
    assert "최신 데이터를 저장하지 못했습니다" in caplog.text
