"""
services/market_data_service.py

시장 데이터 통합 서비스.

- PostgreSQL/Supabase에 저장된 가격 데이터 조회
- KRX 및 보조 데이터 소스를 통한 가격 갱신
- 사용자 포트폴리오 종목의 최신 가격 조회
- 기간별 가격 추이 및 최근 3개월 고점 제공
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from core.config import AppConfig, load_config
from database.models import Price
from database.repository import Repository
from data.price_updater import update_market_prices


logger = logging.getLogger(
    "RetirementPortfolio.MarketDataService"
)


class MarketDataService:
    def __init__(
        self,
        repo: Repository,
        config: Optional[AppConfig] = None,
    ):
        self.repo = repo
        self.config = config or load_config()

    def update_prices(
        self,
        days: int = 90,
        scenario: str = "normal",
    ) -> Dict[str, Any]:
        """현재 사용자의 종목을 포함하여 시장 가격 데이터를 갱신합니다."""
        return update_market_prices(
            config=self.config,
            repo=self.repo,
            user_id=self.repo.user_id,
            days=days,
            scenario=scenario,
        )

    def get_latest_prices(self) -> Dict[str, Price]:
        """
        기본 설정 종목과 현재 사용자의 목표/거래 종목에 대한
        최신 가격 객체 맵을 반환합니다.
        """
        tickers = {
            str(etf.ticker).strip()
            for etf in self.config.etfs
        }

        # 현재 사용자의 계좌 목표 종목
        if self.repo.user_id:
            for target in self.repo.get_account_targets(
                account_id=None
            ):
                tickers.add(
                    str(target.ticker).strip()
                )

            # 현재 사용자의 실제 거래 종목
            for tx in self.repo.get_transactions():
                tickers.add(
                    str(tx.ticker).strip()
                )

        result: Dict[str, Price] = {}

        for ticker in tickers:
            if not ticker:
                continue

            price = self.repo.get_latest_price(ticker)

            if price:
                result[ticker] = price

        return result

    def get_history_by_range(
        self,
        ticker: str,
        period: str = "3m",
    ) -> List[Price]:
        """
        기간별 가격 이력을 조회합니다.

        지원 기간:
        - 3m: 최근 약 3개월
        - 6m: 최근 약 6개월
        - 1y: 최근 1년
        - all: 전체
        """
        now = datetime.now()
        start_date: Optional[str] = None

        if period == "3m":
            start_date = (
                now - timedelta(days=93)
            ).strftime("%Y%m%d")

        elif period == "6m":
            start_date = (
                now - timedelta(days=186)
            ).strftime("%Y%m%d")

        elif period == "1y":
            start_date = (
                now - timedelta(days=365)
            ).strftime("%Y%m%d")

        return self.repo.get_prices(
            ticker,
            start_date=start_date,
        )

    def get_recent_3m_high(
        self,
        ticker: str,
        exclude_today: bool = False,
    ) -> tuple[float, str]:
        """최근 3개월 최고 가격과 발생일을 반환합니다."""
        return self.repo.get_recent_3m_high(
            ticker,
            exclude_today=exclude_today,
        )
