"""Regression checks for average-cost partial sales and PnL breakdown."""
from datetime import date
from types import SimpleNamespace

import pytest

from portfolio.holdings import calculate_etf_positions
from portfolio.performance import calculate_portfolio_summary


def tx(row_id, side, qty, price, *, fee=0, tax=0):
    return SimpleNamespace(
        id=row_id, ticker="AAA", transaction_date=date(2026, 1, row_id),
        transaction_type=side, quantity=qty, price=price, fee=fee, tax=tax,
    )


def position(trades, current_price=150, dividends=()):
    prices = {"AAA": SimpleNamespace(close_price=current_price, price_date=date(2026, 1, 9))}
    result = calculate_etf_positions(
        transactions=trades, dividends=list(dividends),
        latest_prices=prices, ticker_names={"AAA": "Example"},
        ticker_currencies={"AAA": "KRW"}, as_of_date=date(2026, 1, 9),
    )
    return result["AAA"]


def test_partial_sell_preserves_average_cost_and_splits_pnl():
    p = position([tx(1, "BUY", 10, 100), tx(2, "BUY", 10, 120), tx(3, "SELL", 5, 140)])
    assert p.quantity == 15
    assert p.average_buy_price == pytest.approx(110)
    assert p.total_buy_cost == pytest.approx(1650)
    assert p.realized_pnl == pytest.approx(150)
    assert p.unrealized_pnl == pytest.approx(600)
    assert p.total_pnl == pytest.approx(750)


def test_full_sale_resets_cost_basis_before_next_purchase():
    p = position([tx(1, "BUY", 4, 100), tx(2, "SELL", 4, 120), tx(3, "BUY", 2, 80)], current_price=90)
    assert p.quantity == 2
    assert p.average_buy_price == pytest.approx(80)
    assert p.realized_pnl == pytest.approx(80)
    assert p.unrealized_pnl == pytest.approx(20)


def test_historical_fees_and_taxes_affect_realized_pnl():
    p = position([tx(1, "BUY", 10, 100, fee=10), tx(2, "SELL", 4, 120, fee=3, tax=2)])
    assert p.average_buy_price == pytest.approx(101)
    assert p.realized_pnl == pytest.approx(71)
    assert p.total_buy_cost == pytest.approx(606)


def test_summary_adds_realized_and_unrealized_without_double_count():
    p = position([tx(1, "BUY", 10, 100), tx(2, "SELL", 5, 120)], current_price=130)
    summary = calculate_portfolio_summary({"AAA": p}, initial_capital=0, base_currency="KRW")
    assert summary.total_realized_pnl == pytest.approx(100)
    assert summary.total_unrealized_pnl == pytest.approx(150)
    assert summary.total_pnl == pytest.approx(250)
