"""Daily position reconciliation boundary cases for opening snapshot preflight."""
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from services.opening_snapshot_confirmation import check_opening_snapshot_confirmation


def preflight(trades):
    opening = date.today() - timedelta(days=20)
    snapshot = {
        "opening_date": opening.isoformat(),
        "status": "draft",
        "currency": "USD",
        "cash_amount": "100",
        "holdings": [{"ticker": "AAPL", "quantity": "2", "market_value": "200"}],
    }
    events = [
        SimpleNamespace(
            transaction_date=opening + timedelta(days=offset),
            ticker=ticker, transaction_type=side, quantity=quantity,
        )
        for offset, ticker, side, quantity in trades
    ]
    return check_opening_snapshot_confirmation(
        snapshot, transactions=events, account_currency="USD"
    )


def codes(result, group):
    return {item["code"] for item in result[group]}


@pytest.mark.parametrize("quantity", ["3", "2.0001"])
def test_oversell_exceeding_opening_quantity_blocks(quantity):
    result = preflight([(1, "AAPL", "SELL", quantity)])
    assert not result["can_confirm"]
    assert "NEGATIVE_RECONCILED_POSITION" in codes(result, "blockers")


def test_exact_sell_of_opening_quantity_is_not_negative():
    result = preflight([(1, "AAPL", "SELL", "2")])
    assert "NEGATIVE_RECONCILED_POSITION" not in codes(result, "blockers")


def test_prior_day_buy_can_cover_later_sell():
    result = preflight([(1, "AAPL", "BUY", "3"), (2, "AAPL", "SELL", "5")])
    assert "NEGATIVE_RECONCILED_POSITION" not in codes(result, "blockers")


def test_same_day_buy_sell_is_ambiguous_but_net_quantity_is_not_negative():
    result = preflight([(1, "AAPL", "SELL", "5"), (1, "AAPL", "BUY", "3")])
    assert "NEGATIVE_RECONCILED_POSITION" not in codes(result, "blockers")
    assert "SAME_DAY_TRADE_ORDER_UNKNOWN" in codes(result, "warnings")


def test_negative_daily_position_is_not_erased_by_later_buy():
    result = preflight([(1, "AAPL", "SELL", "3"), (2, "AAPL", "BUY", "5")])
    assert "NEGATIVE_RECONCILED_POSITION" in codes(result, "blockers")


@pytest.mark.parametrize("quantity", ["0", "-1", "not-a-number"])
def test_invalid_trade_quantity_blocks(quantity):
    result = preflight([(1, "AAPL", "BUY", quantity)])
    assert "INVALID_TRADE_QUANTITY" in codes(result, "blockers")
