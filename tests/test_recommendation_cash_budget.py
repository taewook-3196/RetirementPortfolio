"""매수 추천 예산과 실제 계좌 현금 연결에 대한 회귀 테스트."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core.config import ETFConfig, get_default_config
from portfolio.holdings import ETFPosition
from services.recommendation_service import RecommendationService
from strategy.recommendation import (
    ETFRecommendationInput,
    generate_recommendations,
)


def _input(
    ticker="A",
    *,
    target_weight=1.0,
    current_value=0.0,
    current_price=100.0,
    recent_high=100.0,
):
    return ETFRecommendationInput(
        ticker=ticker,
        name=ticker,
        target_weight=target_weight,
        current_price=current_price,
        recent_3m_high=recent_high,
        current_asset_value=current_value,
    )


def _total(result):
    return sum(
        item.recommended_buy
        for item in result["recommendations"]
    )


@pytest.mark.parametrize(
    ("available_cash", "base_budget", "expected_total"),
    [
        (1_500.0, 1_000.0, 1_000.0),
        (600.0, 1_000.0, 600.0),
        (0.0, 1_000.0, 0.0),
        (-100.0, 1_000.0, 0.0),
    ],
    ids=[
        "base-budget-is-cap",
        "cash-is-cap",
        "zero-cash",
        "negative-cash",
    ],
)
def test_actual_cash_caps_base_recommendation(
    available_cash,
    base_budget,
    expected_total,
):
    result = generate_recommendations(
        [_input()],
        initial_capital=100_000.0,
        total_invested_so_far=0.0,
        base_monthly=base_budget,
        available_cash=available_cash,
    )

    assert result["summary"]["remaining_cash"] == max(0.0, available_cash)
    assert result["summary"]["total_recommended_buy"] == expected_total
    assert _total(result) == expected_total


def test_base_and_additional_combined_never_exceed_actual_cash():
    result = generate_recommendations(
        [
            _input(
                "UNDER",
                target_weight=0.8,
                current_value=6_000.0,
                current_price=90.0,
                recent_high=100.0,
            ),
            _input(
                "OVER",
                target_weight=0.2,
                current_value=4_000.0,
                current_price=100.0,
                recent_high=100.0,
            ),
        ],
        initial_capital=100_000.0,
        base_monthly=10_000.0,
        max_additional_monthly=20_000.0,
        available_cash=12_000.0,
    )
    summary = result["summary"]

    assert summary["total_additional_buy"] > 0
    assert sum(item.base_buy for item in result["recommendations"]) > 0
    assert summary["total_recommended_buy"] == 12_000.0
    assert _total(result) == 12_000.0
    assert _total(result) <= summary["remaining_cash"]


def test_additional_budget_respects_existing_cycle_usage():
    result = generate_recommendations(
        [
            _input(
                "UNDER",
                target_weight=0.8,
                current_value=6_000.0,
                current_price=90.0,
                recent_high=100.0,
            ),
            _input(
                "OVER",
                target_weight=0.2,
                current_value=4_000.0,
            ),
        ],
        initial_capital=100_000.0,
        base_monthly=0.0,
        max_additional_monthly=20_000.0,
        additional_budget_used=3_000.0,
        available_cash=50_000.0,
    )

    # -10% 낙폭은 추가매수 한도의 25%(5,000)를 허용하고,
    # 이미 사용한 3,000을 제외한 2,000만 새로 추천해야 합니다.
    assert result["summary"]["additional_budget_allowed"] == 5_000.0
    assert result["summary"]["additional_budget_used"] == 3_000.0
    assert result["summary"]["remaining_additional_buy"] == 2_000.0
    assert result["summary"]["total_additional_buy"] == 2_000.0
    assert _total(result) == 2_000.0


def test_projected_portfolio_still_allocates_to_underweight_asset():
    result = generate_recommendations(
        [
            _input("OVER", target_weight=0.60, current_value=70_000.0),
            _input("UNDER", target_weight=0.25, current_value=10_000.0),
            _input("THIRD", target_weight=0.15, current_value=20_000.0),
        ],
        initial_capital=200_000.0,
        base_monthly=10_000.0,
        available_cash=50_000.0,
    )
    recommendations = {
        item.ticker: item
        for item in result["recommendations"]
    }

    assert recommendations["OVER"].base_buy == 0.0
    assert recommendations["UNDER"].base_buy == 10_000.0
    assert recommendations["THIRD"].base_buy == 0.0
    assert _total(result) == 10_000.0


def _recommendation_service(
    accounts,
    cash_by_account,
    *,
    transactions_by_account=None,
):
    repo = Mock()
    repo.get_account.side_effect = lambda account_id: next(
        account
        for account in accounts
        if account.id == account_id
    )
    repo.get_transactions.side_effect = lambda account_id=None: (
        (transactions_by_account or {}).get(account_id, [])
    )
    repo.get_etf_master.return_value = SimpleNamespace(currency="KRW")

    portfolio_service = Mock()
    portfolio_service.get_positions.return_value = {
        "A": ETFPosition(
            ticker="A",
            name="A",
            currency="KRW",
            current_price=100.0,
            current_value=0.0,
        )
    }
    portfolio_service.get_summary.return_value = SimpleNamespace(
        total_invested=0.0,
        currency="KRW",
    )
    portfolio_service.get_target_etfs.return_value = [
        ETFConfig(ticker="A", name="A", target_weight=1.0)
    ]
    portfolio_service.get_cash_balance.side_effect = (
        lambda account_id: cash_by_account[account_id]
    )
    portfolio_service.convert_amount.side_effect = (
        lambda value, from_currency, to_currency: value
    )

    market_service = Mock()
    market_service.get_recent_3m_high.return_value = (100.0, None)

    service = RecommendationService(
        repo,
        get_default_config(),
        market_service=market_service,
        portfolio_service=portfolio_service,
    )
    return service, portfolio_service


def _account(account_id, *, currency="KRW", base=1_000.0, additional=0.0):
    return SimpleNamespace(
        id=account_id,
        initial_capital=100_000.0,
        base_monthly=base,
        max_additional_monthly=additional,
        buy_cycle_type="monthly",
        buy_cycle_detail="25",
        currency=currency,
    )


def test_cycle_spending_and_cash_jointly_cap_remaining_base_budget():
    account = _account(1, base=1_000.0)
    transaction = {
        "ticker": "A",
        "transaction_type": "BUY",
        "transaction_date": date.today(),
        "quantity": 1,
        "price": 400.0,
        "fee": 0.0,
        "tax": 0.0,
    }
    service, _ = _recommendation_service(
        [account],
        {account.id: 500.0},
        transactions_by_account={account.id: [transaction]},
    )

    result = service.calculate_recommendations(
        account_id=account.id,
        auto_save=False,
    )
    summary = result["summary"]

    assert summary["cycle_buy_amount"] == 400.0
    assert summary["remaining_base_budget"] == 600.0
    assert summary["remaining_cash"] == 500.0
    assert summary["total_recommended_buy"] == 500.0


def test_usd_account_compares_usd_cash_and_budget_without_krw_conversion():
    account = _account(1, currency="USD", base=100.0)
    service, portfolio_service = _recommendation_service(
        [account],
        {account.id: 40.0},
    )
    portfolio_service.get_positions.return_value["A"].currency = "USD"
    portfolio_service.get_summary.return_value.currency = "USD"
    service.repo.get_etf_master.return_value = SimpleNamespace(currency="USD")

    result = service.calculate_recommendations(
        account_id=account.id,
        auto_save=False,
    )

    assert result["summary"]["currency"] == "USD"
    assert result["summary"]["remaining_cash"] == 40.0
    assert result["summary"]["total_recommended_buy"] == 40.0
    portfolio_service.get_cash_balance.assert_called_once_with(account_id=1)


def test_account_recommendation_cannot_use_another_accounts_cash():
    account_one = _account(1, base=1_000.0)
    account_two = _account(2, base=1_000.0)
    service, portfolio_service = _recommendation_service(
        [account_one, account_two],
        {account_one.id: 100.0, account_two.id: 50_000.0},
    )

    result = service.calculate_recommendations(
        account_id=account_one.id,
        auto_save=False,
    )

    assert result["summary"]["remaining_cash"] == 100.0
    assert result["summary"]["total_recommended_buy"] == 100.0
    portfolio_service.get_cash_balance.assert_called_once_with(account_id=1)
