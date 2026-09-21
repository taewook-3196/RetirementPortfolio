"""
services/portfolio_service.py
포트폴리오 비즈니스 로직 서비스.
- 거래내역 및 분배금 기반 ETF 보유 현황 및 종합 성과 지표 산출
- 거래 CRUD 제어
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional
from core.config import AppConfig, ETFConfig, load_config
from database.repository import Repository
from database.models import Transaction, Dividend, Price
from portfolio.holdings import ETFPosition, calculate_etf_positions
from portfolio.performance import PortfolioSummary, calculate_portfolio_summary


class PortfolioService:
    def __init__(self, repo: Repository, config: Optional[AppConfig] = None):
        self.repo = repo
        self.config = config or load_config()

    def get_target_etfs(self, account_id: Optional[int] = None) -> List[ETFConfig]:
        """해당 계좌의 목표 ETF 목록(목표 비중 포함)을 반환합니다."""
        targets = self.repo.get_account_targets(account_id)
        if targets:
            return targets
        return self.config.etfs

    def get_positions(
        self,
        latest_prices: Optional[Dict[str, Price] | int] = None,
        account_id: Optional[int] = None,
    ) -> Dict[str, ETFPosition]:
        """모든 ETF의 현재 포지션 및 평단가, 손익 현황을 산출합니다. account_id가 주어지면 해당 계좌만 필터링합니다."""
        if isinstance(latest_prices, int):
            account_id = latest_prices
            latest_prices = None

        txs = self.repo.get_transactions(account_id=account_id)
        divs = self.repo.get_dividends(account_id=account_id)
        target_etfs = self.get_target_etfs(account_id)
        names = {e.ticker: e.name for e in target_etfs}

        for e in self.config.etfs:
            if e.ticker not in names:
                names[e.ticker] = e.name

        for tx in txs:
            if tx.ticker not in names:
                master = self.repo.get_etf_master(tx.ticker)
                names[tx.ticker] = master.name if master else tx.ticker

        if latest_prices is None:
            latest_prices = {}
            all_tickers = set(names.keys()).union({tx.ticker for tx in txs})
            for ticker in all_tickers:
                p = self.repo.get_latest_price(ticker)
                if p:
                    latest_prices[ticker] = p

        return calculate_etf_positions(txs, divs, latest_prices, ticker_names=names)

    def get_summary(
        self,
        positions: Optional[Dict[str, ETFPosition]] = None,
        account_id: Optional[int] = None,
    ) -> PortfolioSummary:
        """포트폴리오 전체 종합 성과 지표를 산출합니다. account_id가 주어지면 해당 계좌의 초기 자본금을 적용합니다."""
        pos = positions if positions is not None else self.get_positions(account_id=account_id)

        # 계좌별 초기 자본금 적용
        if account_id is not None:
            acc = self.repo.get_account(account_id)
            init_cap = int(acc.initial_capital) if acc else self.config.initial_capital
        else:
            # 전체 통합 조회 시: 모든 등록된 계좌의 초기 자본금 합산
            accs = self.repo.get_accounts()
            if accs:
                init_cap = int(sum(a.initial_capital for a in accs))
            else:
                init_cap = self.config.initial_capital

        return calculate_portfolio_summary(pos, initial_capital=init_cap)

