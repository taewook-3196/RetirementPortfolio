"""Regression coverage for optional actual settlement cash movements."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from services.portfolio_service import PortfolioService


def _service(*, settlement_amount=None, settlement_currency=None, side="BUY", fee=0, tax=0):
    account = SimpleNamespace(id=1, currency="KRW", initial_capital=10000)
    trade = SimpleNamespace(
        ticker="TEST", transaction_type=side, quantity=2, price=100,
        fee=fee, tax=tax, settlement_amount=settlement_amount,
        settlement_currency=settlement_currency,
    )
    repo = Mock()
    repo.get_account.return_value = account
    repo.get_cash_flows.return_value = []
    repo.get_transactions.return_value = [trade]
    repo.get_etf_master.return_value = SimpleNamespace(currency="KRW")
    repo.get_dividends.return_value = []
    service = PortfolioService.__new__(PortfolioService)
    service.repo = repo
    service.convert_amount = lambda *, value, from_currency, to_currency: value
    return service


@pytest.mark.parametrize("amount,currency,side,expected", [
    (None, None, "BUY", 9800),
    (None, None, "SELL", 10200),
    (215, "KRW", "BUY", 9785),
    (195, "KRW", "SELL", 10195),
    (215, "USD", "BUY", 9800),
    (195, "USD", "SELL", 10200),
])
def test_settlement_cash_movement(amount, currency, side, expected):
    service = _service(settlement_amount=amount, settlement_currency=currency, side=side)
    assert service.get_cash_balance(1) == expected


def test_legacy_fees_remain_in_cash_calculation():
    service = _service(fee=3, tax=2)
    assert service.get_cash_balance(1) == 9795


def test_initial_capital_exclusion_remains_supported():
    service = _service(settlement_amount=215, settlement_currency="KRW")
    assert service.get_cash_balance(1, include_initial_capital=False) == -215


@pytest.mark.parametrize("invalid", [0, -2, float("nan"), float("inf")])
def test_invalid_confirmed_settlement_is_rejected(invalid):
    service = _service(settlement_amount=invalid, settlement_currency="KRW")
    with pytest.raises(ValueError, match="결제금액"):
        service.get_cash_balance(1)
