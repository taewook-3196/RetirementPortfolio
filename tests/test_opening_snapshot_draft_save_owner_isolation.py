"""API-handler tests for opening snapshot draft save authorization."""
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


def _request(web_app):
    return web_app.OpeningSnapshotDraftRequest(
        opening_date=date(2026, 1, 1),
        cash_amount="100",
        currency="USD",
        holdings=[web_app.OpeningHoldingDraftRequest(ticker="AAPL", quantity="2", market_value="300")],
    )


def test_draft_save_denies_non_owned_account_before_writing(monkeypatch):
    from web import app as web_app

    class FakeRepository:
        def __init__(self, user_id):
            assert user_id == "user-a"

        def get_account(self, account_id):
            assert account_id == 42
            return None

        def save_opening_snapshot_draft(self, **kwargs):
            pytest.fail("Must not write another user's snapshot")

    monkeypatch.setattr(web_app, "get_verified_user_id", lambda token: "user-a")
    monkeypatch.setattr(web_app, "Repository", FakeRepository)
    with pytest.raises(HTTPException) as error:
        web_app.save_opening_snapshot_draft_api(42, _request(web_app), authorization="Bearer test")
    assert error.value.status_code == 404


def test_draft_save_passes_account_scoped_validated_payload(monkeypatch):
    from web import app as web_app

    observed = []

    class FakeRepository:
        def __init__(self, user_id):
            assert user_id == "user-a"

        def get_account(self, account_id):
            observed.append(("account", account_id))
            return SimpleNamespace(id=42, currency="USD")

        def save_opening_snapshot_draft(self, **kwargs):
            observed.append(("save", kwargs))
            return {"saved": True, "status": "draft"}

    monkeypatch.setattr(web_app, "get_verified_user_id", lambda token: "user-a")
    monkeypatch.setattr(web_app, "Repository", FakeRepository)
    result = web_app.save_opening_snapshot_draft_api(42, _request(web_app), authorization="Bearer test")
    assert result == {"saved": True, "status": "draft"}
    assert observed[0] == ("account", 42)
    assert observed[1] == ("save", {
        "account_id": 42, "opening_date": date(2026, 1, 1),
        "cash_amount": "100", "currency": "USD",
        "holdings": [{"ticker": "AAPL", "quantity": "2", "market_value": "300"}],
    })


def test_draft_save_validation_error_is_http_400(monkeypatch):
    from web import app as web_app

    class FakeRepository:
        def __init__(self, user_id):
            pass

        def get_account(self, account_id):
            return SimpleNamespace(id=account_id)

        def save_opening_snapshot_draft(self, **kwargs):
            raise ValueError("잘못된 시작 자산입니다.")

    monkeypatch.setattr(web_app, "get_verified_user_id", lambda token: "user-a")
    monkeypatch.setattr(web_app, "Repository", FakeRepository)
    with pytest.raises(HTTPException) as error:
        web_app.save_opening_snapshot_draft_api(42, _request(web_app), authorization="Bearer test")
    assert error.value.status_code == 400
