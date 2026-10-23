from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from portfolio.krw_cost_basis import calculate_verified_krw_cost_basis


def tx(i, kind, quantity, amount, currency="KRW"):
    return SimpleNamespace(
        id=i, transaction_date=date(2026, 1, i),
        transaction_type=kind, quantity=quantity,
        settlement_amount=amount, settlement_currency=currency,
    )


def test_partial_and_full_sell_with_actual_krw_settlement():
    result = calculate_verified_krw_cost_basis([
        tx(1, "BUY", 10, 140000),
        tx(2, "BUY", 10, 160000),
        tx(3, "SELL", 5, 90000),
    ])
    assert result.verified
    assert result.quantity == Decimal(15)
    assert result.remaining_cost_krw == Decimal(225000)
    assert result.realized_pnl_krw == Decimal(15000)


def test_missing_fx_never_claims_verified():
    result = calculate_verified_krw_cost_basis([
        tx(1, "BUY", 10, None),
        tx(2, "SELL", 2, 50000),
    ])
    assert not result.verified
    assert result.missing_settlement_count == 1


def test_usd_settlement_not_treated_as_krw():
    result = calculate_verified_krw_cost_basis([tx(1, "BUY", 2, 200, "USD")])
    assert not result.verified


def test_oversell_flag():
    result = calculate_verified_krw_cost_basis([
        tx(1, "BUY", 2, 10000),
        tx(2, "SELL", 3, 12000),
    ])
    assert result.oversell_detected
    assert not result.verified


@pytest.mark.parametrize("amount", [0, -1, "NaN", "Infinity"])
def test_invalid_settlement_rejected(amount):
    with pytest.raises(ValueError):
        calculate_verified_krw_cost_basis([tx(1, "BUY", 1, amount)])
