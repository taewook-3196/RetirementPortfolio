"""
services/market_data_service.py
시장 데이터 통합 서비스.
- DB에 캐싱된 가격 데이터 조회
- 필요 시 KRX 또는 Mock 소스로부터 가격 갱신 (비동기 워커 지원)
- 기간별(3개월, 6개월, 1년, 전체) 가격 추이 데이터 제공
"""

from __future__ import annotations
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from core.config import AppConfig, load_config
from database.repository import Repository
from database.models import Price
from data.price_updater import update_market_prices

logger = logging.getLogger("RetirementPortfolio.MarketDataService")


class MarketDataService:
    def __init__(self, repo: Repository, config: Optional[AppConfig] = None):
        self.repo = repo
        self.config = config or load_config()

    def update_prices(self, days: int = 90, scenario: str = "normal") -> Dict[str, Any]:
        """시장 데이터 업데이트 실행"""
        return update_market_prices(
            config=self.config,
            repo=self.repo,
            days=days,
            scenario=scenario,
        )

    def get_latest_prices(self) -> Dict[str, Price]:
        """설정된 모든 ETF의 최신 가격 객체 맵을 반환합니다."""
        res = {}
        for etf in self.config.etfs:
            p = self.repo.get_latest_price(etf.ticker)
            if p:
                res[etf.ticker] = p
        return res

    def get_history_by_range(self, ticker: str, period: str = "3m") -> List[Price]:
        """
        기간별 가격 히스토리 조회 (프롬프트 49번 항목)
        - 3m: 최근 3개월
        - 6m: 최근 6개월
        - 1y: 최근 1년
        - all: 전체
        """
        now = datetime.now()
        start_date = None
        if period == "3m":
            start_date = (now - timedelta(days=93)).strftime("%Y%m%d")
        elif period == "6m":
            start_date = (now - timedelta(days=186)).strftime("%Y%m%d")
        elif period == "1y":
            start_date = (now - timedelta(days=365)).strftime("%Y%m%d")

        return self.repo.get_prices(ticker, start_date=start_date)

    def get_recent_3m_high(self, ticker: str, exclude_today: bool = False) -> tuple[float, str]:
        """최근 3개월 고점 및 발생일 반환 (exclude_today=True 시 직전 고점 반환)"""
        return self.repo.get_recent_3m_high(ticker, exclude_today=exclude_today)
