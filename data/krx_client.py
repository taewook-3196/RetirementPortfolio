"""
data/krx_client.py
한국거래소(KRX) 공식 OPEN API(openapi.krx.co.kr / data-dbg.krx.co.kr) 연동 클라이언트.
- Windows 루트 인증서 신뢰(truststore) 적용
- .env 파일에서 KRX_API_KEY 로드
- 일별 전체 ETF 시세 및 개별 종목 필터링
- 최근 N일 영업일 기준 가격 이력 수집
"""

from __future__ import annotations
import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import requests
from dotenv import load_dotenv

# Windows SSL 인증서 호환성 주입
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

logger = logging.getLogger("RetirementPortfolio.KRXClient")


class KRXClient:
    URL_ETF = "https://data-dbg.krx.co.kr/svc/apis/etp/etf_bydd_trd.json"
    URL_KOSPI = "https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd.json"
    URL_KOSDAQ = "https://data-dbg.krx.co.kr/svc/apis/sto/ksq_bydd_trd.json"

    def __init__(self, api_key: Optional[str] = None):
        load_dotenv()
        self.api_key = (api_key or os.getenv("KRX_API_KEY", "")).strip()
        self.last_stock_master: List[Dict[str, str]] = []
        # 하위 호환용
        self.last_etf_master: List[Dict[str, str]] = []

    def is_configured(self) -> bool:
        """API 키가 설정되어 있는지 확인합니다."""
        return bool(self.api_key)

    def fetch_market_endpoint(self, url: str, date_str: str) -> List[Dict[str, Any]]:
        """특정 시장 엔드포인트의 특정 기준일(YYYYMMDD) 시세 데이터를 수신합니다."""
        if not self.api_key:
            raise ValueError("KRX_API_KEY가 설정되지 않았습니다. .env 파일을 확인해주세요.")

        clean_date = date_str.replace("-", "").strip()
        headers = {
            "AUTH_KEY": self.api_key,
            "User-Agent": "RetirementPortfolio/1.0",
        }
        params = {"basDd": clean_date}

        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code != 200:
            logger.debug("KRX API (%s) HTTP %d: %s", url, response.status_code, response.text[:100])
            return []

        data = response.json()
        return data.get("OutBlock_1", [])

    def fetch_daily_etf_market(self, date_str: str) -> List[Dict[str, Any]]:
        """특정 기준일(YYYYMMDD)의 전체 ETF 시세 데이터를 수신합니다 (기존 호환)."""
        return self.fetch_market_endpoint(self.URL_ETF, date_str)

    def fetch_daily_all_markets(self, date_str: str) -> List[Dict[str, Any]]:
        """
        특정 기준일(YYYYMMDD)의 ETF, 유가증권(KOSPI), 코스닥(KOSDAQ) 전체 시세 데이터를 통합 수신합니다.
        """
        all_rows: List[Dict[str, Any]] = []
        for url in [self.URL_ETF, self.URL_KOSPI, self.URL_KOSDAQ]:
            try:
                rows = self.fetch_market_endpoint(url, date_str)
                if rows:
                    all_rows.extend(rows)
            except Exception as e:
                logger.debug("시장 API (%s) 수신 예외: %s", url, e)
        return all_rows

    def fetch_full_asset_master(
        self,
        date_str: str,
    ) -> List[Dict[str, str]]:
        """
        특정 기준일의 KRX 전체 종목 마스터를 생성합니다.

        ETF, KOSPI, KOSDAQ을 구분하여
        asset_master 저장 형식으로 반환합니다.
        """
        if not self.api_key:
            raise ValueError(
                "KRX_API_KEY가 필요합니다."
            )

        market_sources = [
            (
                self.URL_ETF,
                "ETF",
                "KRX",
            ),
            (
                self.URL_KOSPI,
                "STOCK",
                "KOSPI",
            ),
            (
                self.URL_KOSDAQ,
                "STOCK",
                "KOSDAQ",
            ),
        ]

        master_dict: Dict[
            str,
            Dict[str, str],
        ] = {}

        for (
            url,
            asset_type,
            exchange,
        ) in market_sources:
            try:
                rows = self.fetch_market_endpoint(
                    url,
                    date_str,
                )

                for row in rows:
                    ticker = str(
                        row.get("ISU_CD", "")
                    ).strip()

                    name = str(
                        row.get("ISU_NM", "")
                    ).strip()

                    if not ticker or not name:
                        continue

                    master_dict[ticker] = {
                        "ticker": ticker,
                        "name": name,
                        "market": "KR",
                        "exchange": exchange,
                        "asset_type": asset_type,
                        "currency": "KRW",
                    }

            except Exception as exc:
                logger.warning(
                    "%s 종목 마스터 수집 실패: %s",
                    exchange,
                    exc,
                )

        return list(
            master_dict.values()
        )

    def fetch_historical_prices(
        self,
        target_tickers: List[str],
        days: int = 90,
        end_date: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        최근 days일 동안의 영업일을 순회하며 대상 종목(ETF, KOSPI, KOSDAQ 주식)들의 가격 데이터를 수집합니다.
        """
        if not self.api_key:
            raise ValueError("KRX_API_KEY가 필요합니다.")

        ticker_set = set(t.strip() for t in target_tickers)
        current_dt = end_date or datetime.now()
        collected: List[Dict[str, Any]] = []

        collected_dates = set()

        for offset in range(days * 2):
            dt = current_dt - timedelta(days=offset)
            if dt.weekday() >= 5:  # 토, 일 제외
                continue

            date_str = dt.strftime("%Y%m%d")
            try:
                rows = self.fetch_daily_all_markets(date_str)
                if not rows:
                    continue

                if rows and not self.last_stock_master:
                    # 전체 상장 종목 마스터 (ETF + 유가증권 + 코스닥)
                    master_dict = {}
                    for r in rows:
                        cd = str(r.get("ISU_CD", "")).strip()
                        nm = str(r.get("ISU_NM", "")).strip()
                        if cd and nm and cd not in master_dict:
                            master_dict[cd] = {"ticker": cd, "name": nm}
                    self.last_stock_master = list(master_dict.values())
                    self.last_etf_master = self.last_stock_master

                found_for_date = False
                for r in rows:
                    isu_cd = str(r.get("ISU_CD", "")).strip()
                    if isu_cd in ticker_set:
                        close_p = float(r.get("TDD_CLSPRC", 0) or 0)
                        if close_p <= 0:
                            continue

                        found_for_date = True
                        collected.append({
                            "date": date_str,
                            "ticker": isu_cd,
                            "name": r.get("ISU_NM", ""),
                            "open_price": float(r.get("TDD_OPNPRC", 0) or 0),
                            "high_price": float(r.get("TDD_HGPRC", 0) or 0),
                            "low_price": float(r.get("TDD_LWPRC", 0) or 0),
                            "close_price": close_p,
                            "nav": float(r.get("NAV", 0) or 0),
                            "volume": int(r.get("ACC_TRDVOL", 0) or 0),
                            "trading_value": float(r.get("ACC_TRDVAL", 0) or 0),
                        })

                if found_for_date:
                    collected_dates.add(date_str)
                    if len(collected_dates) >= days:
                        break
            except Exception as e:
                logger.warning("%s 데이터 수신 실패 (휴일 또는 미개장일): %s", date_str, e)

        return collected
