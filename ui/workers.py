"""
ui/workers.py
UI 동결 방지(QThread) 비동기 데이터 작업자.
프롬프트 51번 항목: API 호출 및 데이터 갱신 중에도 GUI가 부드럽게 유지되도록 보장합니다.
"""

from __future__ import annotations
import logging
from PySide6.QtCore import QThread, Signal
from services.market_data_service import MarketDataService

logger = logging.getLogger("RetirementPortfolio.Workers")


class PriceUpdateWorker(QThread):
    """시장 데이터(KRX/Mock)를 비동기로 수집하는 작업자 스레드"""
    started_signal = Signal()
    finished_signal = Signal(dict)
    error_signal = Signal(str)

    def __init__(self, market_service: MarketDataService, days: int = 90, scenario: str = "normal"):
        super().__init__()
        self.market_service = market_service
        self.days = days
        self.scenario = scenario

    def run(self):
        self.started_signal.emit()
        try:
            result = self.market_service.update_prices(days=self.days, scenario=self.scenario)
            self.finished_signal.emit(result)
        except Exception as e:
            logger.exception("비동기 데이터 갱신 중 오류: %s", e)
            self.error_signal.emit(str(e))


class NewsUpdateWorker(QThread):
    """뉴스 데이터를 백그라운드에서 비동기로 수집하는 작업자 스레드"""
    finished_signal = Signal(list)
    error_signal = Signal(str)

    def __init__(self, news_service: Any, mode: str = "all", etfs: list = None, watchlist: list = None):
        super().__init__()
        self.news_service = news_service
        self.mode = mode
        self.etfs = etfs or []
        self.watchlist = watchlist or []

    def run(self):
        try:
            feed = self.news_service.get_news_feed(mode=self.mode, etfs=self.etfs, watchlist=self.watchlist)
            self.finished_signal.emit(feed)
        except Exception as e:
            logger.exception("뉴스 비동기 수집 중 오류: %s", e)
            self.error_signal.emit(str(e))

