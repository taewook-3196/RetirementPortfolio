"""
data/naver_client.py
네이버 증권(Naver Finance) 모바일 API를 통한 국내 ETF 및 주식 실시간/일별 시세 수집기.
- 별도의 API 키나 인증이 필요 없어 안정적이고 즉시 사용 가능
- 최근 90일 일별 시세(시가, 고가, 저가, 종가, 거래량) 수집
- 개별 종목 실시간 현재가 수집
"""

from __future__ import annotations
import json
import logging
import urllib.request
import urllib.parse
from datetime import datetime
from typing import List, Dict, Any, Optional

logger = logging.getLogger("RetirementPortfolio.NaverClient")


class NaverFinanceClient:
    """네이버 금융 모바일 API 클라이언트"""

    BASE_URL = "https://m.stock.naver.com/api/stock"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://m.stock.naver.com/",
        "Accept": "application/json, text/plain, */*",
    }

    def fetch_historical_prices(
        self,
        target_tickers: List[str],
        days: int = 90,
    ) -> List[Dict[str, Any]]:
        """
        대상 종목들의 최근 N일간 일별 가격 데이터를 네이버 금융에서 수집합니다.
        반환 형식은 DB prices 테이블과 호환됩니다:
        [{date: 'YYYYMMDD', ticker: str, name: str, open_price, high_price, low_price, close_price, volume, ...}]
        """
        all_records: List[Dict[str, Any]] = []

        # 네이버 API는 pageSize 최대 60 지원 (60영업일 = 약 3개월 달력일수)
        page_size = 60
        max_pages = 2 if days > 60 else 1

        for ticker in target_tickers:
            t_clean = ticker.strip().upper()
            try:
                # 1. 기본 정보(종목명 등) 조회
                name = self._fetch_stock_name(t_clean) or t_clean

                # 2. 일별 시세 목록 조회 (페이지 순회)
                count = 0
                for page in range(1, max_pages + 1):
                    url = f"{self.BASE_URL}/{t_clean}/price?page={page}&pageSize={page_size}"
                    req = urllib.request.Request(url, headers=self.HEADERS)
                    with urllib.request.urlopen(req, timeout=8) as resp:
                        data = json.loads(resp.read().decode("utf-8"))

                    if not isinstance(data, list) or not data:
                        break

                    for item in data:
                        raw_date = str(item.get("localTradedAt", "")).replace("-", "").strip()
                        if not raw_date or len(raw_date) < 8:
                            continue
                        date_str = raw_date[:8]

                        def _parse_num(val) -> float:
                            if val is None:
                                return 0.0
                            return float(str(val).replace(",", "").strip() or 0)

                        close_p = _parse_num(item.get("closePrice"))
                        open_p = _parse_num(item.get("openPrice")) or close_p
                        high_p = _parse_num(item.get("highPrice")) or max(open_p, close_p)
                        low_p = _parse_num(item.get("lowPrice")) or min(open_p, close_p)
                        volume = int(_parse_num(item.get("accumulatedTradingVolume")))

                        if close_p <= 0:
                            continue

                        all_records.append({
                            "date": date_str,
                            "ticker": t_clean,
                            "name": name,
                            "open_price": open_p,
                            "high_price": high_p,
                            "low_price": low_p,
                            "close_price": close_p,
                            "nav": close_p,
                            "volume": volume,
                            "trading_value": 0.0,
                        })
                        count += 1
                        if count >= days:
                            break

                    if count >= days:
                        break

                logger.debug(f"네이버 금융: {t_clean}({name}) 시세 {count}건 수집 완료")

                logger.debug(f"네이버 금융: {t_clean}({name}) 시세 {count}건 수집 완료")

            except Exception as e:
                logger.warning(f"네이버 금융 ({t_clean}) 시세 수집 중 오류: {e}")

        return all_records

    def _fetch_stock_name(self, ticker: str) -> Optional[str]:
        """종목의 공식 명칭을 조회합니다."""
        try:
            url = f"{self.BASE_URL}/{ticker}/basic"
            req = urllib.request.Request(url, headers=self.HEADERS)
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("stockName")
        except Exception:
            return None
