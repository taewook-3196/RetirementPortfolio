"""
services/portfolio_service.py

포트폴리오 비즈니스 로직 서비스.

- 거래내역 및 분배금 기반 보유 현황 산출
- 종목별 원래 통화 유지
- 계좌 기준통화로 계좌 성과 계산
- 전체 포트폴리오는 계좌별 계산 후 KRW 기준으로 통합
- 사용자별 Repository를 통한 데이터 분리
"""

from __future__ import annotations

from typing import Dict, List, Optional

from core.config import AppConfig, ETFConfig, load_config
from database.models import Price
from database.repository import Repository
from portfolio.holdings import (
    ETFPosition,
    calculate_etf_positions,
)
from portfolio.performance import (
    PortfolioSummary,
    calculate_portfolio_summary,
    convert_currency,
)


class PortfolioService:
    def __init__(
        self,
        repo: Repository,
        config: Optional[AppConfig] = None,
    ):
        self.repo = repo
        self.config = config or load_config()

    # =========================================================
    # 환율
    # =========================================================

    def _get_usd_krw_rate(
        self,
    ) -> Optional[float]:
        """
        DB에 저장된 가장 최근 USD/KRW 환율을 반환합니다.

        유효한 환율이 없으면 None을 반환합니다.

        동일 통화끼리의 계산에는 환율이 필요하지 않습니다.
        실제 KRW/USD 교차 환산이 필요한 경우에만
        convert_currency()가 유효한 환율을 요구합니다.
        """

        exchange_rate = (
            self.repo.get_latest_exchange_rate(
                "USD",
                "KRW",
            )
        )

        if exchange_rate is None:
            return None

        try:
            rate = float(
                exchange_rate.rate
            )
        except (
            TypeError,
            ValueError,
        ):
            return None

        if rate <= 0:
            return None

        return rate
        

    def get_usd_krw_rate(
        self,
    ) -> Optional[float]:
        """
        DB에 저장된 가장 최근 USD/KRW 환율을 반환합니다.

        다른 서비스에서 통화 환산이 필요할 때 사용하는
        공개 인터페이스입니다.
        """
        return self._get_usd_krw_rate()

    def convert_amount(
        self,
        value: float,
        from_currency: str,
        to_currency: str,
    ) -> float:
        """
        금액을 지정한 통화로 변환합니다.

        현재 지원:
        - KRW -> KRW
        - USD -> USD
        - USD -> KRW
        - KRW -> USD

        서로 다른 통화 간 환산이 필요한 경우
        DB에 저장된 최신 USD/KRW 환율을 사용합니다.

        동일 통화끼리는 환율 조회 없이 그대로 반환합니다.
        """

        source_currency = (
            str(
                from_currency
                or "KRW"
            )
            .strip()
            .upper()
        )

        target_currency = (
            str(
                to_currency
                or "KRW"
            )
            .strip()
            .upper()
        )

        amount = float(
            value or 0
        )

        if (
            source_currency
            == target_currency
        ):
            return amount

        usd_krw_rate = (
            self._get_usd_krw_rate()
        )

        return convert_currency(
            value=amount,
            from_currency=source_currency,
            to_currency=target_currency,
            usd_krw_rate=usd_krw_rate,
        )


    # =========================================================
    # 현금 잔고
    # =========================================================

    def get_cash_balance(
        self,
        account_id: int,
        include_initial_capital: bool = False,
    ) -> float:
        """
        특정 계좌의 실제 현금 잔고를 계산합니다.

        계산식:

        시작 현금
        + 입금
        - 출금
        - 매수금액
        - 매수 수수료
        - 매수 세금
        + 매도금액
        - 매도 수수료
        - 매도 세금
        + 배당 실수령액

        모든 금액은 계좌 기준통화로 환산합니다.

        include_initial_capital=False가 기본값입니다.

        현재 initial_capital은 계좌에 따라
        실제 입금액과 투자 설정값의 의미가 섞여 있으므로,
        명시적으로 요청하지 않는 한 현금으로 간주하지 않습니다.
        """

        account = (
            self.repo.get_account(
                account_id
            )
        )

        if account is None:
            raise ValueError(
                "계좌를 찾을 수 없습니다."
            )

        account_currency = (
            str(
                account.currency
                or "KRW"
            )
            .strip()
            .upper()
        )

        cash_balance = 0.0

        # -----------------------------------------------------
        # 1. 초기 투자재원
        # -----------------------------------------------------

        if include_initial_capital:
            cash_balance += float(
                account.initial_capital
                or 0
            )

        # -----------------------------------------------------
        # 2. 실제 입금 / 출금
        # -----------------------------------------------------

        cash_flows = (
            self.repo.get_cash_flows(
                account_id
            )
        )

        for cash_flow in cash_flows:
            amount = self.convert_amount(
                value=float(
                    cash_flow.amount
                    or 0
                ),
                from_currency=str(
                    cash_flow.currency
                    or account_currency
                ),
                to_currency=(
                    account_currency
                ),
            )

            flow_type = (
                str(
                    cash_flow.flow_type
                    or ""
                )
                .strip()
                .upper()
            )

            if flow_type == "DEPOSIT":
                cash_balance += amount

            elif flow_type == "WITHDRAWAL":
                cash_balance -= amount

        # -----------------------------------------------------
        # 3. 매수 / 매도
        # -----------------------------------------------------

        transactions = (
            self.repo.get_transactions(
                account_id=account_id
            )
        )

        asset_currency_cache: Dict[
            str,
            str,
        ] = {}

        for transaction in transactions:
            ticker = str(
                transaction.ticker
                or ""
            ).strip()

            if ticker not in asset_currency_cache:
                asset = (
                    self.repo.get_etf_master(
                        ticker
                    )
                )

                asset_currency_cache[
                    ticker
                ] = (
                    str(
                        getattr(
                            asset,
                            "currency",
                            account_currency,
                        )
                        or account_currency
                    )
                    .strip()
                    .upper()
                )

            transaction_currency = (
                asset_currency_cache[
                    ticker
                ]
            )

            quantity = float(
                transaction.quantity
                or 0
            )

            price = float(
                transaction.price
                or 0
            )

            fee = float(
                transaction.fee
                or 0
            )

            tax = float(
                transaction.tax
                or 0
            )

            gross_amount = (
                quantity * price
            )

            transaction_type = (
                str(
                    transaction.transaction_type
                    or ""
                )
                .strip()
                .upper()
            )

            if transaction_type == "BUY":
                native_cash_change = -(
                    gross_amount
                    + fee
                    + tax
                )

            elif transaction_type == "SELL":
                native_cash_change = (
                    gross_amount
                    - fee
                    - tax
                )

            else:
                continue

            cash_balance += (
                self.convert_amount(
                    value=native_cash_change,
                    from_currency=(
                        transaction_currency
                    ),
                    to_currency=(
                        account_currency
                    ),
                )
            )

        # -----------------------------------------------------
        # 4. 배당 실수령액
        # -----------------------------------------------------

        dividends = (
            self.repo.get_dividends(
                account_id=account_id
            )
        )

        for dividend in dividends:
            cash_balance += (
                self.convert_amount(
                    value=float(
                        dividend.net_amount
                        or 0
                    ),
                    from_currency=str(
                        dividend.currency
                        or account_currency
                    ),
                    to_currency=(
                        account_currency
                    ),
                )
            )

        return round(
            cash_balance,
            2,
        )    

    # =========================================================
    # 목표 종목
    # =========================================================

    def get_target_etfs(
        self,
        account_id: Optional[int] = None,
    ) -> List[ETFConfig]:
        """해당 계좌의 목표 ETF 목록을 반환합니다."""

        targets = self.repo.get_account_targets(
            account_id
        )

        if targets:
            return targets

        # 아직 계좌가 하나도 없는 초기 상태에서만
        # config의 기본 ETF 구성을 사용
        if (
            account_id is None
            and not self.repo.get_accounts()
        ):
            return list(
                self.config.etfs
            )

        return []

    # =========================================================
    # 포지션
    # =========================================================

    def get_positions(
        self,
        latest_prices: Optional[
            Dict[str, Price] | int
        ] = None,
        account_id: Optional[int] = None,
    ) -> Dict[str, ETFPosition]:
        """
        현재 보유 포지션, 평단가 및 손익을 계산합니다.

        ETFPosition 내부의 금액은 종목의 원래 통화를
        그대로 유지합니다.

        account_id가 지정되면 해당 계좌만 계산합니다.
        """

        # 기존 호출 방식과의 호환성 유지
        if isinstance(
            latest_prices,
            int,
        ):
            account_id = latest_prices
            latest_prices = None

        transactions = (
            self.repo.get_transactions(
                account_id=account_id
            )
        )

        dividends = (
            self.repo.get_dividends(
                account_id=account_id
            )
        )

        target_etfs = (
            self.get_target_etfs(
                account_id
            )
        )

        names = {
            etf.ticker: etf.name
            for etf in target_etfs
        }

        # 종목별 원래 거래/가격 통화
        currencies: Dict[
            str,
            str,
        ] = {}

        # 목표 종목의 asset_master에서
        # 이름과 통화 정보를 보완합니다.
        for etf in target_etfs:
            master = (
                self.repo.get_etf_master(
                    etf.ticker
                )
            )

            if master:
                names[etf.ticker] = (
                    master.name
                    or names.get(
                        etf.ticker,
                        etf.ticker,
                    )
                )

                currencies[etf.ticker] = (
                    str(
                        master.currency
                        or "KRW"
                    )
                    .strip()
                    .upper()
                )

        # 계좌가 전혀 없는 초기 상태에서만
        # 기본 config ETF 이름을 사용
        if (
            account_id is None
            and not self.repo.get_accounts()
        ):
            for etf in self.config.etfs:
                if etf.ticker not in names:
                    names[
                        etf.ticker
                    ] = etf.name

                # asset_master가 있으면
                # 실제 통화를 사용합니다.
                if (
                    etf.ticker
                    not in currencies
                ):
                    master = (
                        self.repo
                        .get_etf_master(
                            etf.ticker
                        )
                    )

                    currencies[
                        etf.ticker
                    ] = (
                        str(
                            getattr(
                                master,
                                "currency",
                                "KRW",
                            )
                            or "KRW"
                        )
                        .strip()
                        .upper()
                    )

        # 실제 거래 종목이 목표 종목에
        # 없을 수도 있으므로 asset_master에서
        # 이름과 통화를 보완합니다.
        for tx in transactions:
            ticker = str(
                tx.ticker
            ).strip()

            if (
                ticker not in names
                or ticker not in currencies
            ):
                master = (
                    self.repo
                    .get_etf_master(
                        ticker
                    )
                )

                if master:
                    names[ticker] = (
                        master.name
                        or ticker
                    )

                    currencies[ticker] = (
                        str(
                            master.currency
                            or "KRW"
                        )
                        .strip()
                        .upper()
                    )

                else:
                    names.setdefault(
                        ticker,
                        ticker,
                    )

                    currencies.setdefault(
                        ticker,
                        "KRW",
                    )

        # 가격이 외부에서 전달되지 않았다면
        # DB의 최신 가격 사용
        if latest_prices is None:
            latest_prices = {}

            all_tickers = (
                set(
                    names.keys()
                )
                .union(
                    tx.ticker
                    for tx in transactions
                )
            )

            for ticker in all_tickers:
                price = (
                    self.repo
                    .get_latest_price(
                        ticker
                    )
                )

                if price:
                    latest_prices[
                        ticker
                    ] = price

        return calculate_etf_positions(
            transactions,
            dividends,
            latest_prices,
            ticker_names=names,
            ticker_currencies=currencies,
        )

    # =========================================================
    # 계좌/전체 포트폴리오 요약
    # =========================================================

    def get_summary(
        self,
        positions: Optional[
            Dict[str, ETFPosition]
        ] = None,
        account_id: Optional[int] = None,
    ) -> PortfolioSummary:
        """
        포트폴리오 성과 지표를 계산합니다.

        account_id가 지정된 경우:
            해당 계좌의 Account.currency를
            기준통화로 사용합니다.

        account_id가 None이고 계좌가 존재하는 경우:
            각 계좌를 먼저 각자의 기준통화로 계산한 뒤
            모든 계좌 요약을 KRW로 환산하여 합산합니다.

        따라서 서로 다른 계좌의 거래나 통화를
        직접 섞어서 계산하지 않습니다.
        """


        # -----------------------------------------------------
        # 1. 개별 계좌 요약
        # -----------------------------------------------------

        if account_id is not None:
            account = (
                self.repo.get_account(
                    account_id
                )
            )

            if account:
                initial_capital = float(
                    account.initial_capital
                    or 0
                )

                base_currency = (
                    str(
                        getattr(
                            account,
                            "currency",
                            "KRW",
                        )
                        or "KRW"
                    )
                    .strip()
                    .upper()
                )

            else:
                initial_capital = float(
                    self.config.initial_capital
                )

                base_currency = "KRW"

            if positions is not None:
                current_positions = (
                    positions
                )
            else:
                current_positions = (
                    self.get_positions(
                        account_id=account_id
                    )
                )

            # 계좌 기준통화와 다른 통화의 종목이 있을 때만
            # USD/KRW 환율을 조회합니다.
            needs_fx = any(
                str(
                    position.currency
                    or base_currency
                )
                .strip()
                .upper()
                != base_currency
                for position in current_positions.values()
            )

            usd_krw_rate = (
                self._get_usd_krw_rate()
                if needs_fx
                else None
            )

            return calculate_portfolio_summary(
                current_positions,
                initial_capital=initial_capital,
                base_currency=base_currency,
                usd_krw_rate=usd_krw_rate,
            )

            return calculate_portfolio_summary(
                current_positions,
                initial_capital=initial_capital,
                base_currency=base_currency,
                usd_krw_rate=usd_krw_rate,
            )

        # -----------------------------------------------------
        # 2. 전체 포트폴리오
        # -----------------------------------------------------

        accounts = (
            self.repo.get_accounts()
        )
        # 전체 포트폴리오 계산에서는 USD 계좌 또는
        # 혼합통화 계좌가 존재할 수 있으므로 최신 환율을 준비합니다.
        #
        # 실제 환산이 발생하지 않는 KRW-only 경로에서는
        # convert_currency()가 이 값을 사용하지 않습니다.
        usd_krw_rate = (
            self._get_usd_krw_rate()
        )

        
        # 계좌가 아직 없는 초기 상태에서는
        # 기존 config 기반 계산을 유지합니다.
        if not accounts:
            if positions is not None:
                current_positions = (
                    positions
                )
            else:
                current_positions = (
                    self.get_positions(
                        account_id=None
                    )
                )

            return calculate_portfolio_summary(
                current_positions,
                initial_capital=float(
                    self.config.initial_capital
                ),
                base_currency="KRW",
                usd_krw_rate=usd_krw_rate,
            )

        # -----------------------------------------------------
        # 계좌별로 먼저 계산한 뒤
        # 전체 포트폴리오는 KRW 기준으로 통합합니다.
        # -----------------------------------------------------

        total_initial_capital = 0.0
        total_invested = 0.0
        total_current_value = 0.0
        total_unrealized_pnl = 0.0
        total_realized_pnl = 0.0
        total_dividends = 0.0
        total_remaining_cash = 0.0
        total_position_count = 0

        for account in accounts:
            account_currency = (
                str(
                    getattr(
                        account,
                        "currency",
                        "KRW",
                    )
                    or "KRW"
                )
                .strip()
                .upper()
            )

            account_positions = (
                self.get_positions(
                    account_id=account.id
                )
            )

            account_summary = (
                calculate_portfolio_summary(
                    account_positions,
                    initial_capital=float(
                        account.initial_capital
                        or 0
                    ),
                    base_currency=(
                        account_currency
                    ),
                    usd_krw_rate=(
                        usd_krw_rate
                    ),
                )
            )

            # 각 계좌 요약 금액을
            # 전체 기준통화인 KRW로 변환합니다.
            def to_krw(
                value: float,
            ) -> float:
                return convert_currency(
                    value=value,
                    from_currency=(
                        account_currency
                    ),
                    to_currency="KRW",
                    usd_krw_rate=(
                        usd_krw_rate
                    ),
                )

            total_initial_capital += (
                to_krw(
                    account_summary
                    .initial_capital
                )
            )

            total_invested += (
                to_krw(
                    account_summary
                    .total_invested
                )
            )

            total_current_value += (
                to_krw(
                    account_summary
                    .total_current_value
                )
            )

            total_unrealized_pnl += (
                to_krw(
                    account_summary
                    .total_unrealized_pnl
                )
            )

            total_realized_pnl += (
                to_krw(
                    account_summary
                    .total_realized_pnl
                )
            )

            total_dividends += (
                to_krw(
                    account_summary
                    .total_dividends
                )
            )

            total_remaining_cash += (
                to_krw(
                    account_summary
                    .remaining_cash
                )
            )

            total_position_count += int(
                account_summary
                .position_count
                or 0
            )

        total_pnl = (
            total_unrealized_pnl
            + total_realized_pnl
            + total_dividends
        )

        if total_invested > 0:
            total_roi = (
                total_pnl
                / total_invested
            )
        else:
            total_roi = 0.0

        return PortfolioSummary(
            currency="KRW",

            initial_capital=round(
                total_initial_capital,
                2,
            ),

            total_invested=round(
                total_invested,
                2,
            ),

            total_current_value=round(
                total_current_value,
                2,
            ),

            total_unrealized_pnl=round(
                total_unrealized_pnl,
                2,
            ),

            total_realized_pnl=round(
                total_realized_pnl,
                2,
            ),

            total_dividends=round(
                total_dividends,
                2,
            ),

            total_pnl=round(
                total_pnl,
                2,
            ),

            total_roi=round(
                total_roi,
                6,
            ),

            remaining_cash=round(
                total_remaining_cash,
                2,
            ),

            position_count=(
                total_position_count
            ),
        )
