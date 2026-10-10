"""Market index chart calculations and mobile controls."""
from unittest.mock import patch
import pandas as pd
import pytest
from services.market_index_service import load_index_series, _CACHE
from web.app import home


def test_invalid_index_and_period_rejected_without_external_calls():
    with pytest.raises(ValueError):
        load_index_series("invalid", "1y")
    with pytest.raises(ValueError):
        load_index_series("sp500", "invalid")


def test_index_series_returns_returns_mdd_and_moving_averages():
    dates = pd.date_range(end=pd.Timestamp.now(tz="UTC"), periods=95, freq="D")
    closes = [100.0 + i for i in range(95)]
    closes[-2], closes[-1] = 210.0, 190.0
    frame = pd.DataFrame({"Close": closes}, index=dates)
    class FakeTicker:
        def history(self, **kwargs):
            return frame
    _CACHE.clear()
    with patch("yfinance.Ticker", return_value=FakeTicker()):
        data = load_index_series("sp500", "3m")
    assert data["symbol"] == "^GSPC"
    assert data["points"][-1]["close"] == 190.0
    assert data["points"][-1]["ma20"] is not None
    assert data["points"][-1]["ma60"] is not None
    assert data["max_drawdown_pct"] < 0
    assert isinstance(data["change_pct"], float)


def test_index_mobile_controls(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "public-anon-key")
    html = home().body.decode("utf-8")
    assert 'id="market-index-section"' in html
    assert 'id="market-index-chart"' in html
    assert 'id="market-index-select"' in html
    assert 'data-index-period="5y"' in html
    assert '/api/market-indices/' in html
