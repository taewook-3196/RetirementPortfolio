from datetime import date
from types import SimpleNamespace

from services.opening_snapshot_confirmation import check_opening_snapshot_confirmation


def _snapshot():
    return {
        "status": "draft", "opening_date": "2026-01-01", "cash_amount": "0",
        "currency": "USD", "holdings": [{"ticker": "AAPL", "quantity": "0", "market_value": "0"}],
    }


def _trade(day, side, qty):
    return SimpleNamespace(transaction_date=date(2026, 1, day), ticker="AAPL", transaction_type=side, quantity=str(qty))


def _codes(result, field):
    return {item["code"] for item in result[field]}


def test_same_day_sell_then_buy_does_not_invent_negative_intraday_balance():
    result = check_opening_snapshot_confirmation(_snapshot(), transactions=[_trade(2, "SELL", 3), _trade(2, "BUY", 3)])
    assert "NEGATIVE_RECONCILED_POSITION" not in _codes(result, "blockers")
    assert "SAME_DAY_TRADE_ORDER_UNKNOWN" in _codes(result, "warnings")


def test_same_day_net_sell_beyond_opening_quantity_is_still_blocked():
    result = check_opening_snapshot_confirmation(_snapshot(), transactions=[_trade(2, "SELL", 4), _trade(2, "BUY", 3)])
    assert "NEGATIVE_RECONCILED_POSITION" in _codes(result, "blockers")
    assert "SAME_DAY_TRADE_ORDER_UNKNOWN" in _codes(result, "warnings")


def test_prior_day_buy_covers_later_sell_regardless_of_input_order():
    result = check_opening_snapshot_confirmation(_snapshot(), transactions=[_trade(3, "SELL", 2), _trade(2, "BUY", 2)])
    assert "NEGATIVE_RECONCILED_POSITION" not in _codes(result, "blockers")
