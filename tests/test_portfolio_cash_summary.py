"""PortfolioSummary의 실제 계좌 현금 연동 회귀 테스트."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core.config import get_default_config
from portfolio.holdings import calculate_etf_positions
from services.portfolio_service import PortfolioService


def _repo_with_accounts(accounts, *, exchange_rate=None):
    repo = Mock()
    repo.get_accounts.return_value = accounts
    repo.get_account.side_effect = lambda account_id: next(
        (account for account in accounts if account.id == account_id),
        None,
    )
    repo.get_latest_exchange_rate.return_value = (
        SimpleNamespace(rate=exchange_rate)
        if exchange_rate is not None
        else None
    )
    repo.get_account_targets.return_value = []
    repo.get_transactions.return_value = []
    repo.get_dividends.return_value = []
    repo.get_cash_flows.return_value = []
    repo.get_latest_price.return_value = None
    return repo


def _transaction(
    transaction_id,
    transaction_type,
    quantity,
    price,
    *,
    fee=0.0,
    tax=0.0,
    ticker="TEST",
    transaction_date=date(2026, 1, 1),
):
    return SimpleNamespace(
        id=transaction_id,
        transaction_date=transaction_date,
        ticker=ticker,
        transaction_type=transaction_type,
        quantity=quantity,
        price=price,
        fee=fee,
        tax=tax,
    )


def _dividend(net_amount, *, ticker="TEST", currency="KRW"):
    return SimpleNamespace(
        ticker=ticker,
        net_amount=net_amount,
        currency=currency,
    )


def _price(close_price):
    return SimpleNamespace(close_price=close_price)


@pytest.mark.parametrize(
    ("cash_flows", "transactions", "dividends", "expected_cash"),
    [
        ([], [], [], 10_000.0),
        ([], [_transaction(1, "BUY", 10, 100)], [], 9_000.0),
        (
            [SimpleNamespace(amount=2_000, currency="KRW", flow_type="DEPOSIT")],
            [],
            [],
            12_000.0,
        ),
        (
            [SimpleNamespace(amount=1_500, currency="KRW", flow_type="WITHDRAWAL")],
            [],
            [],
            8_500.0,
        ),
        ([], [_transaction(1, "SELL", 5, 120)], [], 10_600.0),
        ([], [], [_dividend(300)], 10_300.0),
        (
            [],
            [
                _transaction(1, "BUY", 10, 100, fee=10, tax=5),
                _transaction(2, "SELL", 4, 120, fee=4, tax=2),
            ],
            [],
            9_459.0,
        ),
    ],
    ids=[
        "initial-capital-only",
        "buy",
        "deposit",
        "withdrawal",
        "sell",
        "dividend",
        "buy-sell-fees-and-taxes",
    ],
)
def test_cash_balance_components(
    cash_flows,
    transactions,
    dividends,
    expected_cash,
):
    """실제 현금잔고의 각 구성요소를 독립적인 숫자로 검증한다."""
    account = SimpleNamespace(
        id=1,
        initial_capital=10_000.0,
        currency="KRW",
        base_monthly=99_000_000.0,
        max_additional_monthly=88_000_000.0,
    )
    repo = _repo_with_accounts([account])
    repo.get_cash_flows.return_value = cash_flows
    repo.get_transactions.return_value = transactions
    repo.get_dividends.return_value = dividends
    repo.get_etf_master.return_value = SimpleNamespace(currency="KRW")

    service = PortfolioService(repo, get_default_config())

    assert service.get_cash_balance(account.id) == expected_cash


def test_partial_sell_preserves_quantity_cost_and_calculates_all_amounts():
    """부분매도 후 잔여 원가, 현금, 평가/실현/배당 손익과 총자산을 검증한다."""
    buy = _transaction(1, "BUY", 100, 100, fee=100, tax=50)
    partial_sell = _transaction(
        2,
        "SELL",
        40,
        130,
        fee=40,
        tax=20,
        transaction_date=date(2026, 1, 2),
    )
    dividend = _dividend(200)
    positions = calculate_etf_positions(
        [buy, partial_sell],
        [dividend],
        {"TEST": _price(120)},
    )
    position = positions["TEST"]

    account = SimpleNamespace(id=1, initial_capital=20_000.0, currency="KRW")
    repo = _repo_with_accounts([account])
    repo.get_cash_flows.return_value = [
        SimpleNamespace(amount=1_000, currency="KRW", flow_type="DEPOSIT"),
        SimpleNamespace(amount=500, currency="KRW", flow_type="WITHDRAWAL"),
    ]
    repo.get_transactions.return_value = [buy, partial_sell]
    repo.get_dividends.return_value = [dividend]
    repo.get_etf_master.return_value = SimpleNamespace(currency="KRW")
    service = PortfolioService(repo, get_default_config())
    summary = service.get_summary(positions=positions, account_id=account.id)

    assert position.quantity == 60
    assert position.average_buy_price == 101.5
    assert position.total_buy_cost == 6_090.0
    assert position.current_value == 7_200.0
    assert position.unrealized_pnl == 1_110.0
    assert position.realized_pnl == 1_080.0
    assert position.total_dividends == 200.0
    assert position.total_pnl == 2_390.0
    assert position.total_fees == 210.0

    assert summary.total_invested == 6_090.0
    assert summary.total_current_value == 7_200.0
    assert summary.total_unrealized_pnl == 1_110.0
    assert summary.total_realized_pnl == 1_080.0
    assert summary.total_dividends == 200.0
    assert summary.total_pnl == 2_390.0
    assert summary.remaining_cash == 15_690.0
    assert summary.total_current_value + summary.remaining_cash == 22_890.0
    assert summary.position_count == 1


def test_full_sell_clears_position_cost_and_keeps_realized_results():
    """완전매도 후 수량/원가는 0이 되고 누적 실현손익과 현금은 유지된다."""
    transactions = [
        _transaction(1, "BUY", 100, 100, fee=100, tax=50),
        _transaction(
            2,
            "SELL",
            40,
            130,
            fee=40,
            tax=20,
            transaction_date=date(2026, 1, 2),
        ),
        _transaction(
            3,
            "SELL",
            60,
            120,
            fee=60,
            tax=30,
            transaction_date=date(2026, 1, 3),
        ),
    ]
    dividend = _dividend(200)
    positions = calculate_etf_positions(
        transactions,
        [dividend],
        {"TEST": _price(140)},
    )
    position = positions["TEST"]

    account = SimpleNamespace(id=1, initial_capital=20_000.0, currency="KRW")
    repo = _repo_with_accounts([account])
    repo.get_cash_flows.return_value = [
        SimpleNamespace(amount=1_000, currency="KRW", flow_type="DEPOSIT"),
        SimpleNamespace(amount=500, currency="KRW", flow_type="WITHDRAWAL"),
    ]
    repo.get_transactions.return_value = transactions
    repo.get_dividends.return_value = [dividend]
    repo.get_etf_master.return_value = SimpleNamespace(currency="KRW")
    service = PortfolioService(repo, get_default_config())
    summary = service.get_summary(positions=positions, account_id=account.id)

    assert position.quantity == 0
    assert position.average_buy_price == 0
    assert position.total_buy_cost == 0
    assert position.current_value == 0
    assert position.unrealized_pnl == 0
    assert position.realized_pnl == 2_100.0
    assert position.total_dividends == 200.0
    assert position.total_pnl == 2_300.0
    assert position.total_fees == 300.0

    assert summary.total_invested == 0
    assert summary.total_current_value == 0
    assert summary.total_unrealized_pnl == 0
    assert summary.total_realized_pnl == 2_100.0
    assert summary.total_dividends == 200.0
    assert summary.total_pnl == 2_300.0
    assert summary.remaining_cash == 22_800.0
    assert summary.total_current_value + summary.remaining_cash == 22_800.0
    assert summary.position_count == 0


def test_usd_account_and_overall_portfolio_are_aggregated_in_krw():
    """USD 계좌 내부 계산과 KRW/USD 전체 합계를 확정 숫자로 검증한다."""
    krw_account = SimpleNamespace(
        id=1,
        initial_capital=1_000_000.0,
        currency="KRW",
    )
    usd_account = SimpleNamespace(
        id=2,
        initial_capital=1_000.0,
        currency="USD",
    )
    krw_buy = _transaction(
        1,
        "BUY",
        10,
        10_000,
        fee=100,
        tax=50,
        ticker="KRW-ETF",
    )
    usd_buy = _transaction(
        2,
        "BUY",
        2,
        100,
        fee=2,
        tax=1,
        ticker="USD-ETF",
    )
    usd_dividend = _dividend(5, ticker="USD-ETF", currency="USD")

    repo = _repo_with_accounts(
        [krw_account, usd_account],
        exchange_rate=1_350.0,
    )
    repo.get_transactions.side_effect = lambda account_id=None, **_: {
        krw_account.id: [krw_buy],
        usd_account.id: [usd_buy],
    }.get(account_id, [])
    repo.get_dividends.side_effect = lambda account_id=None, **_: {
        krw_account.id: [],
        usd_account.id: [usd_dividend],
    }.get(account_id, [])
    repo.get_cash_flows.side_effect = lambda account_id: (
        [SimpleNamespace(amount=100, currency="USD", flow_type="DEPOSIT")]
        if account_id == usd_account.id
        else []
    )
    repo.get_etf_master.side_effect = lambda ticker: SimpleNamespace(
        name=ticker,
        currency="USD" if ticker == "USD-ETF" else "KRW",
    )
    repo.get_latest_price.side_effect = lambda ticker: {
        "KRW-ETF": _price(12_000),
        "USD-ETF": _price(110),
    }.get(ticker)
    service = PortfolioService(repo, get_default_config())

    usd_summary = service.get_summary(account_id=usd_account.id)
    overall_summary = service.get_summary()

    assert usd_summary.currency == "USD"
    assert usd_summary.initial_capital == 1_000.0
    assert usd_summary.total_invested == 203.0
    assert usd_summary.total_current_value == 220.0
    assert usd_summary.total_unrealized_pnl == 17.0
    assert usd_summary.total_realized_pnl == 0.0
    assert usd_summary.total_dividends == 5.0
    assert usd_summary.total_pnl == 22.0
    assert usd_summary.remaining_cash == 902.0
    assert usd_summary.total_current_value + usd_summary.remaining_cash == 1_122.0

    assert overall_summary.currency == "KRW"
    assert overall_summary.initial_capital == 2_350_000.0
    assert overall_summary.total_invested == 374_200.0
    assert overall_summary.total_current_value == 417_000.0
    assert overall_summary.total_unrealized_pnl == 42_800.0
    assert overall_summary.total_realized_pnl == 0.0
    assert overall_summary.total_dividends == 6_750.0
    assert overall_summary.total_pnl == 49_550.0
    assert overall_summary.remaining_cash == 2_117_550.0
    assert (
        overall_summary.total_current_value
        + overall_summary.remaining_cash
        == 2_534_550.0
    )
    assert overall_summary.position_count == 2


def test_account_summary_remaining_cash_uses_actual_cash_balance():
    account = SimpleNamespace(
        id=1,
        initial_capital=1_000_000.0,
        currency="KRW",
    )
    repo = _repo_with_accounts([account])
    repo.get_cash_flows.return_value = [
        SimpleNamespace(amount=200_000.0, currency="KRW", flow_type="DEPOSIT"),
        SimpleNamespace(amount=50_000.0, currency="KRW", flow_type="WITHDRAWAL"),
    ]
    repo.get_transactions.return_value = [
        SimpleNamespace(
            ticker="KRW-ETF",
            transaction_type="BUY",
            quantity=10,
            price=10_000.0,
            fee=1_000.0,
            tax=500.0,
        ),
        SimpleNamespace(
            ticker="KRW-ETF",
            transaction_type="SELL",
            quantity=2,
            price=12_000.0,
            fee=200.0,
            tax=100.0,
        ),
    ]
    repo.get_etf_master.return_value = SimpleNamespace(currency="KRW")
    repo.get_dividends.return_value = [
        SimpleNamespace(net_amount=10_000.0, currency="KRW"),
    ]
    service = PortfolioService(repo, get_default_config())

    expected_cash = 1_000_000 + 200_000 - 50_000 - 101_500 + 23_700 + 10_000
    summary = service.get_summary(positions={}, account_id=account.id)

    assert service.get_cash_balance(account.id) == expected_cash
    assert summary.remaining_cash == expected_cash
    assert summary.remaining_cash != account.initial_capital - summary.total_invested

    repo.get_transactions.assert_called_with(account_id=account.id)
    repo.get_dividends.assert_called_with(account_id=account.id)
    repo.get_cash_flows.assert_called_with(account.id)


def test_overall_summary_sums_each_account_cash_in_krw():
    krw_account = SimpleNamespace(
        id=1,
        initial_capital=1_000_000.0,
        currency="KRW",
    )
    usd_account = SimpleNamespace(
        id=2,
        initial_capital=1_000.0,
        currency="USD",
    )
    repo = _repo_with_accounts(
        [krw_account, usd_account],
        exchange_rate=1_350.0,
    )
    repo.get_cash_flows.side_effect = lambda account_id: (
        [SimpleNamespace(amount=100.0, currency="USD", flow_type="DEPOSIT")]
        if account_id == usd_account.id
        else []
    )
    service = PortfolioService(repo, get_default_config())
    service.get_positions = Mock(return_value={})

    summary = service.get_summary()

    assert summary.currency == "KRW"
    assert summary.remaining_cash == 1_000_000 + (1_000 + 100) * 1_350
    assert repo.get_cash_flows.call_count == 2
