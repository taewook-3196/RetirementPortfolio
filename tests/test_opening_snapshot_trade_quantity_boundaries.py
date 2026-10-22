"""Regression tests for post-opening trade quantity reconciliation."""
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from services.opening_snapshot_confirmation import check_opening_snapshot_confirmation


def opening_snapshot():
    return {
        "opening_date": (date.today() - timedelta(days=15)).isoformat(),
        "currency": "USD",
        "cash_amount": "100",
        "status": "draft",
        "holdings": [{"ticker": "AAPL", "quantity": "2", "market_value": "200"}],
    }


def trade(days, ticker, side, quantity):
    return SimpleNamespace(
        transaction_date=date.today() - timedelta(days=15 - days),
        ticker=ticker,
        transaction_type=side,
        quantity=quantity,
    )


@pytest.mark.parametrize(
    ("trades", "negative"),
    [
        ([trade(1, "AAPL", "SELL", "3")], True),
        ([trade(1, "AAPL", "SELL", "2")], False),
        ([trade(1, "AAPL", "BUY", "1"), trade(2, "AAPL", "SELL", "3")], False),
        ([trade(1, "AAPL", "SELL", "3"), trade(2, "AAPL", "BUY", "2")], True),
        ([trade(1, "AAPL", "SELL", "3"), trade(1, "AAPL", "BUY", "2")], False),
    ],
)
def test_daily_reconciled_quantities(trades, negative):
    result = check_opening_snapshot_confirmation(opening_snapshot(), transactions=trades, account_currency="USD")
    codes = {item["code"] for item in result["blockers"]}
    assert ("NEGATIVE_RECONCILED_POSITION" in codes) is negative


def test_same_day_buy_sell_warns_about_unknown_execution_order():
    result = check_opening_snapshot_confirmation(
        opening_snapshot(),
        transactions=[trade(1, "AAPL", "SELL", "3"), trade(1, "AAPL", "BUY", "2")],
        account_currency="USD",
    )
    assert "SAME_DAY_TRADE_ORDER_UNKNOWN" in {item["code"] for item in result["warnings"]}
    assert not result["can_confirm"]


@pytest.mark.parametrize("quantity", ["0", "-1", "NaN", "Infinity", "bad"])
def test_invalid_trade_quantity_blocks_confirmation(quantity):
    result = check_opening_snapshot_confirmation(
        opening_snapshot(), transactions=[trade(1, "AAPL", "BUY", quantity)], account_currency="USD"
    )
    assert "INVALID_TRADE_QUANTITY" in {item["code"] for item in result["blockers"]}
