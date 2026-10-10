"""User-scoped watchlist API and mobile UI regression tests."""
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
import pytest

from web.app import (
    WatchlistSaveRequest,
    get_user_watchlist,
    save_user_watchlist,
    delete_user_watchlist,
    home,
)


class FakeRepo:
    rows = []
    owner_ids = []
    def __init__(self, user_id):
        self.user_id = user_id
        self.owner_ids.append(user_id)
    def get_watchlist(self):
        return list(self.rows)
    def add_watchlist(self, ticker, memo=""):
        if ticker == "UNKNOWN":
            raise ValueError("등록되지 않은 종목")
        self.rows.append({"ticker": ticker, "name": ticker, "memo": memo})
    def remove_watchlist(self, ticker):
        old = len(self.rows)
        self.rows = [row for row in self.rows if row["ticker"] != ticker]
        return len(self.rows) < old


@pytest.fixture(autouse=True)
def clear_state():
    FakeRepo.rows = []
    FakeRepo.owner_ids = []


def test_watchlist_crud_auth_and_normalization():
    with patch("web.app.get_verified_user_id", return_value="member-1"), patch("web.app.Repository", FakeRepo):
        assert get_user_watchlist(authorization="Bearer token") == {"items": []}
        added = save_user_watchlist(WatchlistSaveRequest(ticker=" aapl ", memo="tech"), authorization="Bearer token")
        assert added["items"][0]["ticker"] == "AAPL"
        assert delete_user_watchlist("aapl", authorization="Bearer token") == {"items": []}
        assert FakeRepo.owner_ids == ["member-1"] * 3


def test_watchlist_rejects_invalid_and_missing():
    with patch("web.app.get_verified_user_id", return_value="member-2"), patch("web.app.Repository", FakeRepo):
        with pytest.raises(HTTPException) as error:
            save_user_watchlist(WatchlistSaveRequest(ticker="UNKNOWN"), authorization="Bearer token")
        assert error.value.status_code == 400
        with pytest.raises(HTTPException) as error:
            delete_user_watchlist("MISSING", authorization="Bearer token")
        assert error.value.status_code == 404


def test_watchlist_mobile_controls_and_safe_dom(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "public-anon-key")
    html = home().body.decode("utf-8")
    for marker in ('id="watchlist-section"', 'id="watchlist-search-form"', 'id="watchlist-items"', 'id="watchlist-status"', 'portfolio: ["portfolio-section", "watchlist-section", "asset-search-section"]'):
        assert marker in html
    assert 'watchlistNode("strong", item.name || item.ticker)' in html
    assert 'watchlistSearchResults.replaceChildren()' in html
