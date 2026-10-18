"""API-level tests for opening snapshot preflight account ownership and read-only behavior."""
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


def test_preflight_rejects_account_owned_by_another_user(monkeypatch):
    from web import app as web_app

    class FakeRepository:
        def __init__(self, user_id):
            assert user_id == "user-a"

        def get_account(self, account_id):
            assert account_id == 42
            return None

        def get_opening_snapshot(self, account_id):
            pytest.fail("Must not read another user's opening snapshot")

        def get_transactions(self, **kwargs):
            pytest.fail("Must not read another user's transactions")

    monkeypatch.setattr(web_app, "get_verified_user_id", lambda token: "user-a")
    monkeypatch.setattr(web_app, "Repository", FakeRepository)
    with pytest.raises(HTTPException) as error:
        web_app.get_opening_snapshot_preflight_api(42, authorization="Bearer test")
    assert error.value.status_code == 404


def test_preflight_reads_only_requested_account_and_never_saves(monkeypatch):
    from web import app as web_app

    observed = []
    snapshot = {
        "status": "draft", "opening_date": "2026-01-01",
        "currency": "USD", "cash_amount": "0", "holdings": [],
    }

    class FakeRepository:
        def __init__(self, user_id):
            assert user_id == "user-a"

        def get_account(self, account_id):
            observed.append(("account", account_id))
            return SimpleNamespace(id=42, currency="USD") if account_id == 42 else None

        def get_opening_snapshot(self, account_id):
            observed.append(("snapshot", account_id))
            return snapshot

        def get_transactions(self, account_id):
            observed.append(("transactions", account_id))
            return []

        def get_cash_flows(self, account_id):
            observed.append(("cash_flows", account_id))
            return []

        def get_dividends(self, account_id):
            observed.append(("dividends", account_id))
            return []

        def save_opening_snapshot_draft(self, *args, **kwargs):
            pytest.fail("Preflight must never write a draft")

    monkeypatch.setattr(web_app, "get_verified_user_id", lambda token: "user-a")
    monkeypatch.setattr(web_app, "Repository", FakeRepository)
    result = web_app.get_opening_snapshot_preflight_api(42, authorization="Bearer test")
    assert result["can_confirm"] is True
    assert observed == [
        ("account", 42), ("snapshot", 42), ("transactions", 42),
        ("cash_flows", 42), ("dividends", 42),
    ]
