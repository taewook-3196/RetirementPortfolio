"""
services/recommendation_service.py

매수 추천 및 리밸런싱 비즈니스 로직 서비스.

- 사용자 포트폴리오와 최신 시장 가격 집계
- 최근 3개월 고점 계산
- 계좌별 투자 주기 및 예산 반영
- 매수 추천 결과 생성 및 RecommendationLog 저장
- 리밸런싱 추천 결과 생성
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.config import AppConfig, ETFConfig, load_config
from database.repository import Repository
from services.market_data_service import MarketDataService
from services.portfolio_service import PortfolioService
from strategy.cycle_helper import get_cycle_buy_amount
from strategy.recommendation import (
    ETFRecommendationInput,
    generate_recommendations,
)


class RecommendationService:
    def __init__(
        self,
        repo: Repository,
        config: Optional[AppConfig] = None,
        market_service: Optional[MarketDataService] = None,
        portfolio_service: Optional[PortfolioService] = None,
    ):
        self.repo = repo
        self.config = config or load_config()

        self.market_service = (
            market_service
            or MarketDataService(repo, self.config)
        )

        self.portfolio_service = (
            portfolio_service
            or PortfolioService(repo, self.config)
        )

    def calculate_recommendations(
        self,
        account_id: Optional[int] = None,
        auto_save: bool = True,
    ) -> Dict[str, Any]:
        """
        포트폴리오 현황과 시장 가격을 이용하여
        매수 추천 결과를 계산합니다.

        단순히 이번 주기에 BUY 거래가 존재하는지를
        판단하지 않고, 실제 BUY 금액을 기준으로
        남은 기본 매수 한도를 계산합니다.
        """
        cfg = self.config

        positions = (
            self.portfolio_service
            .get_positions(
                account_id=account_id
            )
        )

        summary = (
            self.portfolio_service
            .get_summary(
                positions,
                account_id=account_id,
            )
        )

        cycle_desc = ""
        cycle_buy_amount = 0.0

        # ---------------------------------------------------------
        # 계좌별 투자 예산
        # ---------------------------------------------------------

        if account_id is not None:

            account = self.repo.get_account(
                account_id
            )

            if account:

                initial_capital = float(
                    account.initial_capital
                    or 0
                )

                base_monthly = float(
                    account.base_monthly
                    or 0
                )

                max_additional_monthly = float(
                    account.max_additional_monthly
                    or 0
                )

                cycle_type = (
                    account.buy_cycle_type
                    or "monthly"
                )

                cycle_detail = (
                    account.buy_cycle_detail
                    or "25"
                )

                transactions = (
                    self.repo.get_transactions(
                        account_id=account_id
                    )
                )

                (
                    cycle_buy_amount,
                    _last_buy_dt,
                    cycle_desc,
                ) = get_cycle_buy_amount(
                    transactions,
                    cycle_type,
                    cycle_detail,
                )

            else:

                initial_capital = float(
                    cfg.initial_capital
                )

                base_monthly = float(
                    cfg.base_monthly
                )

                max_additional_monthly = float(
                    cfg.max_additional_monthly
                )

        else:

            accounts = (
                self.repo.get_accounts()
            )

            if accounts:

                initial_capital = sum(
                    float(
                        account.initial_capital
                        or 0
                    )
                    for account in accounts
                )

                base_monthly = sum(
                    float(
                        account.base_monthly
                        or 0
                    )
                    for account in accounts
                )

                max_additional_monthly = sum(
                    float(
                        account.max_additional_monthly
                        or 0
                    )
                    for account in accounts
                )

            else:

                initial_capital = float(
                    cfg.initial_capital
                )

                base_monthly = float(
                    cfg.base_monthly
                )

                max_additional_monthly = float(
                    cfg.max_additional_monthly
                )

            default_account = (
                self.repo.get_default_account()
            )

            cycle_type = (
                default_account.buy_cycle_type
                if default_account
                and default_account.buy_cycle_type
                else "monthly"
            )

            cycle_detail = (
                default_account.buy_cycle_detail
                if default_account
                and default_account.buy_cycle_detail
                else "25"
            )

            transactions = (
                self.repo.get_transactions()
            )

            (
                cycle_buy_amount,
                _last_buy_dt,
                cycle_desc,
            ) = get_cycle_buy_amount(
                transactions,
                cycle_type,
                cycle_detail,
            )

        # 이번 주기 기본매수 한도 중
        # 아직 사용하지 않은 금액
        remaining_base_budget = max(
            0.0,
            base_monthly
            - cycle_buy_amount,
        )

        base_budget_used = min(
            base_monthly,
            cycle_buy_amount,
        )

        # 기본 한도를 초과하여 이미 매수한 금액은
        # 이번 주기의 추가매수 사용액으로 간주
        additional_budget_used = max(
            0.0,
            cycle_buy_amount
            - base_monthly,
        )

        remaining_additional_budget = max(
            0.0,
            max_additional_monthly
            - additional_budget_used,
        )

        # ---------------------------------------------------------
        # 목표 종목 + 실제 보유 중인 비목표 종목
        # ---------------------------------------------------------

        target_etfs = (
            self.portfolio_service
            .get_target_etfs(
                account_id
            )
        )

        target_tickers = {
            etf.ticker
            for etf in target_etfs
        }

        extra_items: List[
            ETFConfig
        ] = []

        for ticker, position in (
            positions.items()
        ):
            quantity = float(
                position.quantity
                or 0
            )

            total_buy_cost = float(
                position.total_buy_cost
                or 0
            )

            if (
                ticker
                not in target_tickers
                and (
                    quantity > 0
                    or total_buy_cost > 0
                )
            ):
                extra_items.append(
                    ETFConfig(
                        ticker=ticker,
                        name=(
                            position.name
                            or ticker
                        ),
                        target_weight=0.0,
                    )
                )

        all_etfs = (
            target_etfs
            + extra_items
        )

        # ---------------------------------------------------------
        # 추천 엔진 입력
        # ---------------------------------------------------------

        inputs: List[
            ETFRecommendationInput
        ] = []

        for etf in all_etfs:

            position = positions.get(
                etf.ticker
            )

            current_price = (
                float(
                    position.current_price
                    or 0
                )
                if position
                else 0.0
            )

            holding_quantity = (
                float(
                    position.quantity
                    or 0
                )
                if position
                else 0.0
            )

            current_asset_value = (
                float(
                    position.current_value
                    or 0
                )
                if position
                else 0.0
            )

            recent_high, _ = (
                self.market_service
                .get_recent_3m_high(
                    etf.ticker
                )
            )

            recent_high = float(
                recent_high
                or 0
            )

            if recent_high <= 0:
                recent_high = (
                    current_price
                )

            inputs.append(
                ETFRecommendationInput(
                    ticker=etf.ticker,
                    name=etf.name,
                    target_weight=float(
                        etf.target_weight
                        or 0
                    ),
                    current_price=(
                        current_price
                    ),
                    recent_3m_high=(
                        recent_high
                    ),
                    holding_quantity=(
                        holding_quantity
                    ),
                    current_asset_value=(
                        current_asset_value
                    ),
                )
            )

        # ---------------------------------------------------------
        # 추천 계산
        # ---------------------------------------------------------

        result = (
            generate_recommendations(
                inputs=inputs,
                initial_capital=(
                    initial_capital
                ),
                base_monthly=(
                    remaining_base_budget
                ),
                max_additional_monthly=(
                    max_additional_monthly
                ),
                additional_budget_used=(
                    additional_budget_used
                ),
                total_invested_so_far=float(
                    summary.total_invested
                    or 0
                ),
                already_invested_in_cycle=False,
                cycle_desc=cycle_desc,
            )
        )

        result_summary = (
            result.get(
                "summary",
                {}
            )
        )

        # 원래 계좌 한도와 이번 주기 사용액을
        # 결과에 명시적으로 추가
        result_summary.update(
            {
                "configured_base_budget":
                    base_monthly,

                "configured_additional_budget":
                    max_additional_monthly,

                "cycle_buy_amount":
                    cycle_buy_amount,

                "base_budget_used":
                    base_budget_used,

                "remaining_base_budget":
                    remaining_base_budget,

                "additional_budget_used":
                    additional_budget_used,

                "remaining_additional_budget":
                    remaining_additional_budget,

                # 기존 UI와의 호환성.
                # 기본/추가 한도를 모두 소진한 경우에만
                # 이번 주기 투자가 완료된 것으로 봅니다.
                "already_invested_in_cycle":
                    (
                        remaining_base_budget
                        <= 0
                        and
                        not bool(
                            result_summary.get(
                                "additional_buy_triggered",
                                False,
                            )
                        )
                    ),

                "cycle_desc":
                    cycle_desc,
            }
        )

        # ---------------------------------------------------------
        # 추천 결과 저장
        # ---------------------------------------------------------

        if (
            auto_save
            and result.get(
                "recommendations"
            )
        ):
            recommendations_to_save = [
                {
                    "ticker":
                        recommendation.ticker,

                    "name":
                        recommendation.name,

                    "target_weight":
                        float(
                            recommendation
                            .target_weight
                            or 0
                        ),

                    "current_weight":
                        float(
                            recommendation
                            .current_weight
                            or 0
                        ),

                    "weight_gap":
                        float(
                            recommendation
                            .weight_gap
                            or 0
                        ),

                    "recent_high":
                        float(
                            recommendation
                            .recent_high
                            or 0
                        ),

                    "current_price":
                        float(
                            recommendation
                            .current_price
                            or 0
                        ),

                    "drawdown":
                        float(
                            recommendation
                            .drawdown
                            or 0
                        ),

                    "drawdown_score":
                        int(
                            recommendation
                            .drawdown_score
                            or 0
                        ),

                    "priority_score":
                        float(
                            recommendation
                            .priority_score
                            or 0
                        ),

                    "recommended_buy":
                        float(
                            recommendation
                            .recommended_buy
                            or 0
                        ),

                    "expected_weight_after":
                        float(
                            recommendation
                            .expected_weight_after
                            or 0
                        ),

                    "reason":
                        (
                            recommendation.reason
                            or ""
                        ),
                }
                for recommendation
                in result[
                    "recommendations"
                ]
            ]

            self.repo.save_recommendations(
                recommendations_to_save
            )

        return result
    def calculate_rebalancing(
        self,
        account_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        추가 자금 투입 없이 현재 보유 자산을 기준으로
        리밸런싱 추천 결과를 계산합니다.
        """
        from strategy.rebalancing import (
            ETFRebalanceInput,
            generate_rebalancing_recommendations,
        )

        positions = (
            self.portfolio_service.get_positions(
                account_id=account_id
            )
        )

        summary = (
            self.portfolio_service.get_summary(
                positions,
                account_id=account_id,
            )
        )

        target_etfs = (
            self.portfolio_service.get_target_etfs(
                account_id
            )
        )

        target_tickers = {
            etf.ticker
            for etf in target_etfs
        }

        extra_items: List[ETFConfig] = []

        for ticker, position in positions.items():
            quantity = float(
                position.quantity or 0
            )

            total_buy_cost = float(
                position.total_buy_cost or 0
            )

            if (
                ticker not in target_tickers
                and (
                    quantity > 0
                    or total_buy_cost > 0
                )
            ):
                extra_items.append(
                    ETFConfig(
                        ticker=ticker,
                        name=position.name or ticker,
                        target_weight=0.0,
                    )
                )

        all_etfs = target_etfs + extra_items

        inputs: List[ETFRebalanceInput] = []

        for etf in all_etfs:
            position = positions.get(etf.ticker)

            current_price = (
                float(position.current_price or 0)
                if position
                else 0.0
            )

            holding_quantity = (
                float(position.quantity or 0)
                if position
                else 0.0
            )

            current_asset_value = (
                float(position.current_value or 0)
                if position
                else 0.0
            )

            # 당일 가격을 제외한 직전 3개월 고점
            recent_high, _ = (
                self.market_service.get_recent_3m_high(
                    etf.ticker,
                    exclude_today=True,
                )
            )

            recent_high = float(
                recent_high or 0
            )

            # 과거 가격이 부족하면 당일 포함 고점 사용
            if recent_high <= 0:
                recent_high, _ = (
                    self.market_service.get_recent_3m_high(
                        etf.ticker,
                        exclude_today=False,
                    )
                )

                recent_high = float(
                    recent_high or 0
                )

            if recent_high <= 0:
                recent_high = current_price

            inputs.append(
                ETFRebalanceInput(
                    ticker=etf.ticker,
                    name=etf.name,
                    target_weight=float(
                        etf.target_weight or 0
                    ),
                    current_price=current_price,
                    recent_3m_high=recent_high,
                    holding_quantity=holding_quantity,
                    current_asset_value=current_asset_value,
                )
            )

        return generate_rebalancing_recommendations(
            inputs=inputs,
            total_portfolio_value=float(
                summary.total_current_value or 0
            ),
        )
