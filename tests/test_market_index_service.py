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



def test_index_rejects_incomplete_history_instead_of_reporting_false_return():
    dates = pd.date_range(end=pd.Timestamp.now(tz="UTC"), periods=5, freq="D")
    frame = pd.DataFrame({"Close": [100.0, 102.0, 101.0, 103.0, 105.0]}, index=dates)

    class FakeTicker:
        def history(self, **kwargs):
            return frame

    _CACHE.clear()
    with patch("yfinance.Ticker", return_value=FakeTicker()):
        with pytest.raises(RuntimeError, match="부족"):
            load_index_series("sp500", "1y")


def test_index_rejects_series_entirely_outside_requested_period():
    dates = pd.date_range(end=pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=90), periods=5, freq="D")
    frame = pd.DataFrame({"Close": [100.0] * 5}, index=dates)

    class FakeTicker:
        def history(self, **kwargs):
            return frame

    _CACHE.clear()
    with patch("yfinance.Ticker", return_value=FakeTicker()):
        with pytest.raises(RuntimeError, match="해당"):
            load_index_series("sp500", "1m")



def test_index_rejects_stale_last_close_even_with_full_period_coverage():
    dates = pd.date_range(
        end=pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=12),
        periods=390, freq="D",
    )
    frame = pd.DataFrame({"Close": [100.0 + i / 10 for i in range(390)]}, index=dates)

    class FakeTicker:
        def history(self, **kwargs):
            return frame

    _CACHE.clear()
    with patch("yfinance.Ticker", return_value=FakeTicker()):
        with pytest.raises(RuntimeError, match="오래되었습니다"):
            load_index_series("sp500", "1y")


def test_index_sorts_prices_and_excludes_future_observations():
    dates = pd.date_range(end=pd.Timestamp.now(tz="UTC").normalize(), periods=105, freq="D")
    closes = [100.0 + i for i in range(105)]
    frame = pd.DataFrame({"Close": closes}, index=dates)
    future = pd.DataFrame(
        {"Close": [99999.0]},
        index=[pd.Timestamp.now(tz="UTC").normalize() + pd.Timedelta(days=3)],
    )
    frame = pd.concat([future, frame.iloc[::-1]])
    class FakeTicker:
        def history(self, **kwargs):
            return frame
    _CACHE.clear()
    with patch("yfinance.Ticker", return_value=FakeTicker()):
        result = load_index_series("sp500", "3m")
    assert result["points"][-1]["close"] == 204.0
    assert all(point["close"] != 99999.0 for point in result["points"])
    assert result["points"] == sorted(result["points"], key=lambda p: p["date"])
