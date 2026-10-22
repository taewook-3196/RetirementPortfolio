"""Opening snapshot quantity reconstruction is conservative about trade ordering."""
from datetime import date, timedelta
from types import SimpleNamespace

from services.opening_snapshot_confirmation import check_opening_snapshot_confirmation


def _snapshot():
    return {
        "opening_date": (date.today() - timedelta(days=10)).isoformat(),
        "status": "draft",
        "currency": "USD",
        "cash_amount": "100",
        "holdings": [{"ticker": "AAPL", "quantity": "2", "market_value": "200"}],
    }


def _trade(days_after, ticker, side, quantity):
    return SimpleNamespace(
        transaction_date=date.today() - timedelta(days=10) + timedelta(days=days_after),
        ticker=ticker,
        transaction_type=side,
        quantity=quantity,
    )


def _codes(result, key):
    return {entry["code"] for entry in result[key]}


def test_sell_beyond_opening_position_blocks_confirmation():
    result = check_opening_snapshot_confirmation(
        _snapshot(), transactions=[_trade(1, "AAPL", "SELL", "3")], account_currency="USD"
    )
    assert "NEGATIVE_RECONCILED_POSITION" in _codes(result, "blockers")
    assert not result["can_confirm"]


def test_prior_buy_can_cover_later_sell_without_negative_blocker():
    result = check_opening_snapshot_confirmation(
        _snapshot(),
        transactions=[_trade(1, "AAPL", "BUY", "2"), _trade(2, "AAPL", "SELL", "3")],
        account_currency="USD",
    )
    assert "NEGATIVE_RECONCILED_POSITION" not in _codes(result, "blockers")
    assert "HOLDINGS_RECONCILIATION_REQUIRED" in _codes(result, "warnings")


def test_same_day_buy_sell_warns_but_does_not_infer_execution_order():
    result = check_opening_snapshot_confirmation(
        _snapshot(),
        transactions=[_trade(1, "AAPL", "SELL", "3"), _trade(1, "AAPL", "BUY", "2")],
        account_currency="USD",
    )
    assert "SAME_DAY_TRADE_ORDER_UNKNOWN" in _codes(result, "warnings")
    assert "NEGATIVE_RECONCILED_POSITION" not in _codes(result, "blockers")
    assert not result["can_confirm"]


def test_invalid_trade_quantity_blocks_confirmation():
    result = check_opening_snapshot_confirmation(
        _snapshot(), transactions=[_trade(1, "AAPL", "SELL", "not-a-number")], account_currency="USD"
    )
    assert "INVALID_TRADE_QUANTITY" in _codes(result, "blockers")
    assert not result["can_confirm"]
