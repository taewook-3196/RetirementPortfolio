"""
services/portfolio_service.py

포트폴리오 비즈니스 로직 서비스.

- 거래내역 및 분배금 기반 보유 현황 산출
- 계좌별/전체 포트폴리오 성과 계산
- 사용자별 Repository를 통한 데이터 분리
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.config import AppConfig, ETFConfig, load_config
from database.models import Price
from database.repository import Repository
from portfolio.holdings import ETFPosition, calculate_etf_positions
from portfolio.performance import PortfolioSummary, calculate_portfolio_summary


class PortfolioService:
    def __init__(
        self,
        repo: Repository,
        config: Optional[AppConfig] = None,
    ):
        self.repo = repo
        self.config = config or load_config()

    def get_target_etfs(
        self,
        account_id: Optional[int] = None,
    ) -> List[ETFConfig]:
        """해당 계좌의 목표 ETF 목록을 반환합니다."""
        targets = self.repo.get_account_targets(account_id)

        if targets:
            return targets

        # 아직 계좌가 하나도 없는 초기 상태에서만
        # config의 기본 ETF 구성을 사용
        if account_id is None and not self.repo.get_accounts():
            return list(self.config.etfs)

        return []

    def get_positions(
        self,
        latest_prices: Optional[Dict[str, Price] | int] = None,
        account_id: Optional[int] = None,
    ) -> Dict[str, ETFPosition]:
        """
        현재 보유 포지션, 평단가 및 손익을 계산합니다.

        account_id가 지정되면 해당 계좌만 계산합니다.
        """
        # 기존 호출 방식과의 호환성 유지
        if isinstance(latest_prices, int):
            account_id = latest_prices
            latest_prices = None

        transactions = self.repo.get_transactions(
            account_id=account_id
        )

        dividends = self.repo.get_dividends(
            account_id=account_id
        )

        target_etfs = self.get_target_etfs(account_id)

        names = {
            etf.ticker: etf.name
            for etf in target_etfs
        }

        # 계좌가 전혀 없는 초기 상태에서만
        # 기본 config ETF 이름을 사용
        if account_id is None and not self.repo.get_accounts():
            for etf in self.config.etfs:
                if etf.ticker not in names:
                    names[etf.ticker] = etf.name

        # 실제 거래 종목이 목표 종목에 없을 수도 있으므로
        # asset_master에서 이름을 보완
        for tx in transactions:
            if tx.ticker not in names:
                master = self.repo.get_etf_master(tx.ticker)

                names[tx.ticker] = (
                    master.name
                    if master
                    else tx.ticker
                )

        # 가격이 외부에서 전달되지 않았다면
        # DB의 최신 가격 사용
        if latest_prices is None:
            latest_prices = {}

            all_tickers = set(names.keys()).union(
                tx.ticker
                for tx in transactions
            )

            for ticker in all_tickers:
                price = self.repo.get_latest_price(ticker)

                if price:
                    latest_prices[ticker] = price

        return calculate_etf_positions(
            transactions,
            dividends,
            latest_prices,
            ticker_names=names,
        )

    def get_summary(
        self,
        positions: Optional[Dict[str, ETFPosition]] = None,
        account_id: Optional[int] = None,
    ) -> PortfolioSummary:
        """
        포트폴리오 전체 성과 지표를 계산합니다.

        account_id가 지정되면 해당 계좌의 초기 자본금을 사용합니다.
        """
        if positions is not None:
            current_positions = positions
        else:
            current_positions = self.get_positions(
                account_id=account_id
            )

        if account_id is not None:
            account = self.repo.get_account(account_id)

            if account:
                initial_capital = float(
                    account.initial_capital or 0
                )
            else:
                initial_capital = float(
                    self.config.initial_capital
                )

        else:
            accounts = self.repo.get_accounts()

            if accounts:
                initial_capital = sum(
                    float(account.initial_capital or 0)
                    for account in accounts
                )
            else:
                initial_capital = float(
                    self.config.initial_capital
                )

        return calculate_portfolio_summary(
            current_positions,
            initial_capital=initial_capital,
        )
