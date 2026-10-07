"""
services/recommendation_service.py

매수 추천 및 리밸런싱 비즈니스 로직 서비스.

- 사용자 포트폴리오와 최신 시장 가격 집계
- 최근 3개월 고점 계산
- 계좌별 투자 주기 및 예산 반영
- 혼합통화 계좌의 금액을 계좌 기준통화로 환산
- 매수 추천 결과 생성 및 RecommendationLog 저장
- 리밸런싱 추천 결과 생성

통화 처리 원칙:
- ETFPosition의 가격/평가액은 종목의 원래 통화를 유지합니다.
- 추천 엔진에 전달하는 금액은 계좌 기준통화로 통일합니다.
- 추천 매수금액(recommended_buy)도 계좌 기준통화입니다.
- 실제 주문 가능 주수 계산은 DailyReportService 등
  표시/주문 계층에서 종목 원래 통화 가격을 사용합니다.
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
            or MarketDataService(
                repo,
                self.config,
            )
        )

        self.portfolio_service = (
            portfolio_service
            or PortfolioService(
                repo,
                self.config,
            )
        )

    # =========================================================
    # 통화 보조 함수
    # =========================================================

    @staticmethod
    def _normalize_currency(
        currency: Optional[str],
        default: str = "KRW",
    ) -> str:
        """
        통화 코드를 대문자로 정규화합니다.
        """
        return (
            str(
                currency
                or default
            )
            .strip()
            .upper()
        )

    def _get_asset_currency(
        self,
        ticker: str,
        fallback: str = "KRW",
    ) -> str:
        """
        asset_master에서 종목의 원래 거래 통화를 조회합니다.

        asset_master에 종목이 없으면 fallback을 사용합니다.
        """
        master = (
            self.repo.get_etf_master(
                ticker
            )
        )

        if master is None:
            return self._normalize_currency(
                fallback
            )

        return self._normalize_currency(
            getattr(
                master,
                "currency",
                fallback,
            ),
            fallback,
        )

    @staticmethod
    def _get_transaction_ticker(
        transaction: Any,
    ) -> str:
        """
        dict 또는 SQLAlchemy Transaction 객체에서
        ticker를 가져옵니다.
        """
        if isinstance(
            transaction,
            dict,
        ):
            return str(
                transaction.get(
                    "ticker",
                    "",
                )
                or ""
            ).strip()

        return str(
            getattr(
                transaction,
                "ticker",
                "",
            )
            or ""
        ).strip()

    def _convert_amount(
        self,
        value: float,
        from_currency: str,
        to_currency: str,
    ) -> float:
        """
        PortfolioService의 공통 환산 기능을 사용하여
        금액을 지정 통화로 변환합니다.
        """
        return float(
            self.portfolio_service
            .convert_amount(
                value=float(
                    value or 0
                ),
                from_currency=(
                    from_currency
                ),
                to_currency=(
                    to_currency
                ),
            )
        )

    # =========================================================
    # 매수 추천
    # =========================================================

    def calculate_recommendations(
        self,
        account_id: Optional[int] = None,
        auto_save: bool = True,
    ) -> Dict[str, Any]:
        """
        포트폴리오 현황과 시장 가격을 이용하여
        매수 추천 결과를 계산합니다.

        account_id가 지정된 경우:
        - 계좌의 기준통화를 확인합니다.
        - 이번 주기 BUY 거래금액을 계좌통화로 환산합니다.
        - 종목 평가액을 계좌통화로 환산합니다.
        - 현재가와 최근 3개월 고점도 동일한 계좌통화로
          환산한 뒤 추천 엔진에 전달합니다.
        - recommended_buy는 계좌 기준통화 금액입니다.

        account_id가 None인 기존 통합 호출은
        현재 호환성을 위해 유지합니다.
        다중 계좌 통합 추천은 이후 계좌별 결과를
        묶는 구조로 별도 전환합니다.
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

        # 기본값
        account_currency = "KRW"
        available_cash: Optional[float] = None

        # ---------------------------------------------------------
        # 1. 계좌별 투자 예산
        # ---------------------------------------------------------

        if account_id is not None:

            account = (
                self.repo.get_account(
                    account_id
                )
            )

            if account:

                account_currency = (
                    self._normalize_currency(
                        getattr(
                            account,
                            "currency",
                            "KRW",
                        )
                    )
                )

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

                # 추천 예산의 최종 상한은 투자원금 잔여액이
                # 아니라 이 계좌의 실제 현금잔고입니다.
                # get_cash_balance()는 계좌 기준통화로 반환합니다.
                available_cash = (
                    self.portfolio_service
                    .get_cash_balance(
                        account_id=account.id
                    )
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

                # -------------------------------------------------
                # 각 BUY 거래를 종목 원래 통화에서
                # 계좌 기준통화로 변환한 뒤
                # 이번 주기 매수금액을 합산합니다.
                #
                # 현재 Transaction에 체결 당시 환율 또는
                # settlement_amount가 없으므로
                # 서로 다른 통화의 과거 거래는
                # 최신 저장 환율을 이용한 근사치입니다.
                # -------------------------------------------------

                def convert_cycle_buy_amount(
                    transaction: Any,
                    native_buy_amount: float,
                ) -> float:
                    ticker = (
                        self._get_transaction_ticker(
                            transaction
                        )
                    )

                    asset_currency = (
                        self._get_asset_currency(
                            ticker,
                            fallback=(
                                account_currency
                            ),
                        )
                    )

                    return self._convert_amount(
                        value=(
                            native_buy_amount
                        ),
                        from_currency=(
                            asset_currency
                        ),
                        to_currency=(
                            account_currency
                        ),
                    )

                (
                    cycle_buy_amount,
                    _last_buy_dt,
                    cycle_desc,
                ) = get_cycle_buy_amount(
                    transactions,
                    cycle_type,
                    cycle_detail,
                    amount_converter=(
                        convert_cycle_buy_amount
                    ),
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

                account_currency = "KRW"

        # ---------------------------------------------------------
        # 기존 account_id=None 통합 호출
        #
        # 현재 DailyReportService와의 호환성을 위해
        # 유지합니다.
        #
        # 여러 통화 계좌의 예산을 하나로 합치는 구조는
        # 정확하지 않으므로 이후 계좌별 추천 결과를
        # 통합 표시하는 방식으로 제거할 예정입니다.
        # ---------------------------------------------------------

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
                if (
                    default_account
                    and default_account.buy_cycle_type
                )
                else "monthly"
            )

            cycle_detail = (
                default_account.buy_cycle_detail
                if (
                    default_account
                    and default_account.buy_cycle_detail
                )
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

        # ---------------------------------------------------------
        # 2. 이번 주기 남은 기본/추가 매수 한도
        # ---------------------------------------------------------

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
        # 3. 목표 종목 + 실제 보유 중인 비목표 종목
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
        # 4. 추천 엔진 입력
        #
        # account_id가 지정된 경우 모든 금액을
        # account_currency로 통일합니다.
        #
        # current_price와 recent_high도 동일 환율로
        # 변환하므로 drawdown 비율 자체는 변하지 않습니다.
        # ---------------------------------------------------------

        inputs: List[
            ETFRecommendationInput
        ] = []

        for etf in all_etfs:

            position = positions.get(
                etf.ticker
            )

            native_current_price = (
                float(
                    position.current_price
                    or 0
                )
                if (
                    position
                    and position.market_price_available
                )
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

            native_current_asset_value = (
                float(
                    position.current_value
                    or 0
                )
                if position
                else 0.0
            )

            # position에 저장된 통화를 우선 사용합니다.
            # 아직 position이 없는 목표 종목은
            # asset_master에서 조회합니다.
            if position:
                asset_currency = (
                    self._normalize_currency(
                        getattr(
                            position,
                            "currency",
                            None,
                        )
                        or self._get_asset_currency(
                            etf.ticker,
                            fallback=(
                                account_currency
                            ),
                        )
                    )
                )
            else:
                asset_currency = (
                    self._get_asset_currency(
                        etf.ticker,
                        fallback=(
                            account_currency
                        ),
                    )
                )

            native_recent_high, _ = (
                self.market_service
                .get_recent_3m_high(
                    etf.ticker
                )
            )

            native_recent_high = float(
                native_recent_high
                or 0
            )

            if native_recent_high <= 0:
                native_recent_high = (
                    native_current_price
                )

            # -----------------------------------------------------
            # 개별 계좌 추천:
            # 종목 native 통화 → 계좌 기준통화
            # -----------------------------------------------------

            if account_id is not None:

                current_price = (
                    self._convert_amount(
                        value=(
                            native_current_price
                        ),
                        from_currency=(
                            asset_currency
                        ),
                        to_currency=(
                            account_currency
                        ),
                    )
                )

                current_asset_value = (
                    self._convert_amount(
                        value=(
                            native_current_asset_value
                        ),
                        from_currency=(
                            asset_currency
                        ),
                        to_currency=(
                            account_currency
                        ),
                    )
                )

                recent_high = (
                    self._convert_amount(
                        value=(
                            native_recent_high
                        ),
                        from_currency=(
                            asset_currency
                        ),
                        to_currency=(
                            account_currency
                        ),
                    )
                )

            # -----------------------------------------------------
            # 기존 통합 호출:
            # 현재 호환성을 위해 기존 native 값 유지
            # -----------------------------------------------------

            else:

                current_price = (
                    native_current_price
                )

                current_asset_value = (
                    native_current_asset_value
                )

                recent_high = (
                    native_recent_high
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
        # 5. 추천 계산
        #
        # 개별 계좌에서는 여기로 들어오는 모든 금액이
        # account_currency 기준입니다.
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
                currency=account_currency,
                available_cash=available_cash,
            )
        )

        result_summary = (
            result.get(
                "summary",
                {}
            )
        )

        # ---------------------------------------------------------
        # 6. 계좌 한도/주기 사용액/통화 정보 추가
        # ---------------------------------------------------------

        result_summary.update(
            {
                "currency":
                    (
                        account_currency
                        if account_id
                        is not None
                        else getattr(
                            summary,
                            "currency",
                            "KRW",
                        )
                    ),

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
        # 7. 추천 결과 저장
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

    # =========================================================
    # 리밸런싱
    # =========================================================

    def calculate_rebalancing(
        self,
        account_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        추가 자금 투입 없이 현재 보유 자산을 기준으로
        리밸런싱 추천 결과를 계산합니다.

        account_id가 지정된 경우 종목별 평가액과 가격을
        계좌 기준통화로 통일한 뒤 계산합니다.
        """
        from strategy.rebalancing import (
            ETFRebalanceInput,
            generate_rebalancing_recommendations,
        )

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

        # ---------------------------------------------------------
        # 계좌 기준통화
        # ---------------------------------------------------------

        account_currency = "KRW"

        if account_id is not None:
            account = (
                self.repo.get_account(
                    account_id
                )
            )

            if account:
                account_currency = (
                    self._normalize_currency(
                        getattr(
                            account,
                            "currency",
                            "KRW",
                        )
                    )
                )

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

        inputs: List[
            ETFRebalanceInput
        ] = []

        for etf in all_etfs:

            position = (
                positions.get(
                    etf.ticker
                )
            )

            native_current_price = (
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

            native_current_asset_value = (
                float(
                    position.current_value
                    or 0
                )
                if position
                else 0.0
            )

            if position:
                asset_currency = (
                    self._normalize_currency(
                        getattr(
                            position,
                            "currency",
                            None,
                        )
                        or self._get_asset_currency(
                            etf.ticker,
                            fallback=(
                                account_currency
                            ),
                        )
                    )
                )
            else:
                asset_currency = (
                    self._get_asset_currency(
                        etf.ticker,
                        fallback=(
                            account_currency
                        ),
                    )
                )

            # 당일 가격을 제외한 직전 3개월 고점
            native_recent_high, _ = (
                self.market_service
                .get_recent_3m_high(
                    etf.ticker,
                    exclude_today=True,
                )
            )

            native_recent_high = float(
                native_recent_high
                or 0
            )

            # 과거 가격이 부족하면 당일 포함 고점 사용
            if native_recent_high <= 0:
                native_recent_high, _ = (
                    self.market_service
                    .get_recent_3m_high(
                        etf.ticker,
                        exclude_today=False,
                    )
                )

                native_recent_high = float(
                    native_recent_high
                    or 0
                )

            if native_recent_high <= 0:
                native_recent_high = (
                    native_current_price
                )

            # -----------------------------------------------------
            # 개별 계좌 리밸런싱:
            # 종목 native 통화 → 계좌 기준통화
            # -----------------------------------------------------

            if account_id is not None:

                current_price = (
                    self._convert_amount(
                        value=(
                            native_current_price
                        ),
                        from_currency=(
                            asset_currency
                        ),
                        to_currency=(
                            account_currency
                        ),
                    )
                )

                current_asset_value = (
                    self._convert_amount(
                        value=(
                            native_current_asset_value
                        ),
                        from_currency=(
                            asset_currency
                        ),
                        to_currency=(
                            account_currency
                        ),
                    )
                )

                recent_high = (
                    self._convert_amount(
                        value=(
                            native_recent_high
                        ),
                        from_currency=(
                            asset_currency
                        ),
                        to_currency=(
                            account_currency
                        ),
                    )
                )

            else:

                current_price = (
                    native_current_price
                )

                current_asset_value = (
                    native_current_asset_value
                )

                recent_high = (
                    native_recent_high
                )

            inputs.append(
                ETFRebalanceInput(
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

        return (
            generate_rebalancing_recommendations(
                inputs=inputs,
                total_portfolio_value=float(
                    summary.total_current_value
                    or 0
                ),
            )
        )
