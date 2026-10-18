"""Regression checks for US ETF lookup and literal Kakao newline artifacts."""
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from data.yfinance_client import YFinanceClient


def test_us_etf_uses_fast_info_currency_when_quote_omits_it():
    fake = SimpleNamespace(
        info={"quoteType": "ETF", "exchange": "PCX", "shortName": "ProShares UltraPro QQQ"},
        fast_info={"currency": "USD"},
    )
    with patch.dict(sys.modules, {"yfinance": SimpleNamespace(Ticker=lambda _: fake)}):
        asset = YFinanceClient().fetch_asset_info("tqqq")
    assert asset["ticker"] == "TQQQ"
    assert asset["currency"] == "USD"
    assert asset["asset_type"] == "ETF"


def test_us_etf_does_not_accept_explicit_non_usd_currency():
    fake = SimpleNamespace(
        info={"quoteType": "ETF", "exchange": "PCX", "currency": "KRW"},
        fast_info={"currency": "USD"},
    )
    with patch.dict(sys.modules, {"yfinance": SimpleNamespace(Ticker=lambda _: fake)}):
        with pytest.raises(ValueError, match="USD"):
            YFinanceClient().fetch_asset_info("tqqq")


def test_kakao_buttons_do_not_render_literal_backslash_n():
    from web.app import home
    response = home()
    html = response.body.decode("utf-8")
    assert '</button>\\n<button id="kakao-test-button"' not in html
    assert '</button>\\n<button id="kakao-disconnect-button"' not in html


def test_us_etf_uses_history_instrument_type_when_quote_type_missing():
    fake = SimpleNamespace(
        info={"exchange": "PCX", "currency": "USD", "shortName": "ProShares UltraPro QQQ"},
        get_history_metadata=lambda: {"instrumentType": "ETF"},
    )
    with patch.dict(sys.modules, {"yfinance": SimpleNamespace(Ticker=lambda _: fake)}):
        asset = YFinanceClient().fetch_asset_info("tqqq")
    assert asset["asset_type"] == "ETF"
    assert asset["ticker"] == "TQQQ"


def test_us_etf_rejects_missing_type_without_verified_metadata():
    fake = SimpleNamespace(
        info={"exchange": "PCX", "currency": "USD"},
        get_history_metadata=lambda: {},
    )
    with patch.dict(sys.modules, {"yfinance": SimpleNamespace(Ticker=lambda _: fake)}):
        with pytest.raises(ValueError, match="UNKNOWN"):
            YFinanceClient().fetch_asset_info("tqqq")
