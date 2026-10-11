"""Sector momentum calculation and mobile UI regression tests."""
from datetime import date, timedelta
from unittest.mock import patch

import pytest
from services.sector_momentum_service import (
    _CACHE, _return_for_period, load_sector_momentum,
)
from web.app import home


def test_period_returns_require_baseline_and_newer_data():
    today = date.today()
    values = [(today - timedelta(days=100), 100), (today, 120)]
    assert _return_for_period(values, today - timedelta(days=90)) == 0.0
    assert _return_for_period(values, today - timedelta(days=110)) == 20.0


def test_non_trading_boundary_uses_next_available_close():
    today = date.today()
    values = [(today - timedelta(days=95), 100), (today - timedelta(days=88), 110), (today, 121)]
    assert _return_for_period(values, today - timedelta(days=90)) == 10.0


def test_invalid_market_rejected():
    with pytest.raises(ValueError):
        load_sector_momentum("invalid")


def test_sector_ranking_and_benchmark_relative_performance():
    today = date.today()
    dates = [today - timedelta(days=400 - i) for i in range(401)]
    def fake_history(symbol, start, end):
        multiplier = 1.5 if symbol == "XLK" else 1.2
        return [(d, 100 + i * (multiplier - 1)) for i, d in enumerate(dates)]
    _CACHE.clear()
    with patch("services.sector_momentum_service._close_history", side_effect=fake_history):
        result = load_sector_momentum("us")
    assert result["items"][0]["ticker"] == "XLK"
    assert result["items"][0]["relative_pct_points"]["3m"] > 0
    assert result["items"][0]["rank_3m"] == 1
    assert result["source"] == "Yahoo Finance (ETF adjusted closes)"


def test_sector_mobile_controls(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "public-anon-key")
    html = home().body.decode("utf-8")
    assert 'id="sector-momentum-section"' in html
    assert 'id="sector-market-select"' in html
    assert 'id="sector-period-select"' in html
    assert '/api/sector-momentum/' in html
    assert 'refreshSectorMomentum()' in html
