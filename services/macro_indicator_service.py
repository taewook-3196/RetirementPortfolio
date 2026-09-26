"""
services/macro_indicator_service.py

데일리 모닝 리포트 및 Gemini AI용 글로벌 매크로 지표 수집기.

시장 지표
- 미국: S&P500, Nasdaq 100, Dow
- 한국: KOSPI, KOSDAQ
- WTI
- 미국 10년물 국채금리
- USD/KRW

미국 경제지표
- 근원 PCE 물가:
  BEA NIPA Table 2.8.4(T20804)의
  PCE excluding food and energy 기반 전년동월비 자동 계산
- 비농업 고용:
  BLS CES0000000001 기반 월간 증감 자동 계산
- 실업률:
  BLS LNS14000000

경제지표 조회에 실패한 경우
오래된 하드코딩 값을 대신 사용하지 않습니다.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import ssl
import urllib.parse
import urllib.request
from typing import Any, Dict, List

logger = logging.getLogger(
    "RetirementPortfolio.MacroIndicatorService"
)


# ============================================================
# Yahoo Finance 시장 지표
# ============================================================

YAHOO_SYMBOLS: Dict[str, Dict[str, Any]] = {
    "sp500": {
        "symbol": "^GSPC",
        "name": "S&P 500",
        "category": "us_market",
        "unit": "pt",
        "decimals": 2,
    },
    "nasdaq100": {
        "symbol": "^NDX",
        "name": "Nasdaq 100",
        "category": "us_market",
        "unit": "pt",
        "decimals": 2,
    },
    "dow": {
        "symbol": "^DJI",
        "name": "다우존스 (DOW)",
        "category": "us_market",
        "unit": "pt",
        "decimals": 2,
    },
    "kospi": {
        "symbol": "^KS11",
        "name": "코스피 (KOSPI)",
        "category": "kr_market",
        "unit": "pt",
        "decimals": 2,
    },
    "kosdaq": {
        "symbol": "^KQ11",
        "name": "코스닥 (KOSDAQ)",
        "category": "kr_market",
        "unit": "pt",
        "decimals": 2,
    },
    "wti_oil": {
        "symbol": "CL=F",
        "name": "WTI 국제유가",
        "category": "macro_commodity",
        "unit": "$",
        "decimals": 2,
    },
    "us10y_yield": {
        "symbol": "^TNX",
        "name": "미국 10년물 국채금리",
        "category": "macro_commodity",
        "unit": "%",
        "decimals": 2,
    },
    "usd_krw": {
        "symbol": "KRW=X",
        "name": "원/달러 환율",
        "category": "macro_commodity",
        "unit": "원",
        "decimals": 1,
    },
}


# ============================================================
# 공식 경제지표
# ============================================================

BLS_API_URL = (
    "https://api.bls.gov/publicAPI/v2/timeseries/data/"
)

BLS_NFP_SERIES = "CES0000000001"
BLS_UNEMPLOYMENT_SERIES = "LNS14000000"


BEA_API_URL = "https://apps.bea.gov/api/data/"

BEA_CORE_PCE_TABLE = "T20804"

# Table 2.8.4
# Line 25 = PCE excluding food and energy
BEA_CORE_PCE_LINE_NUMBER = "25"

BEA_CORE_PCE_DESCRIPTION = (
    "PCE excluding food and energy"
)


class MacroIndicatorService:
    """글로벌 시장 및 미국 경제지표 수집 서비스"""

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )

    def __init__(self):
        self.ssl_context = ssl._create_unverified_context()

    # ========================================================
    # 전체 수집
    # ========================================================

    def fetch_all_macro_data(self) -> Dict[str, Any]:
        """
        시장지표와 미국 주요 경제지표를 일괄 수집합니다.
        """

        results: Dict[str, Any] = {
            "us_market": {},
            "kr_market": {},
            "macro_commodity": {},
            "fundamentals": {},
            "raw_items": {},
        }

        # Yahoo 시장지표
        for key, meta in YAHOO_SYMBOLS.items():
            data = self._fetch_single_yahoo_indicator(
                key,
                meta,
            )

            results["raw_items"][key] = data

            category = meta.get(
                "category",
                "macro_commodity",
            )

            if category in results:
                results[category][key] = data

        # 공식 미국 경제지표
        results["fundamentals"] = (
            self._fetch_us_economic_indicators()
        )

        return results

    # ========================================================
    # Yahoo Finance
    # ========================================================

    def _fetch_single_yahoo_indicator(
        self,
        key: str,
        meta: Dict[str, Any],
    ) -> Dict[str, Any]:

        sym = meta["symbol"]
        name = meta["name"]
        unit = meta["unit"]
        decimals = meta["decimals"]

        default_result = {
            "key": key,
            "name": name,
            "symbol": sym,
            "price": 0.0,
            "price_str": "조회 실패",
            "change_pct": 0.0,
            "change_str": "-",
            "trend": "UNKNOWN",
            "trend_badge": "데이터 없음",
            "5d_change_pct": 0.0,
            "5d_change_bp": None,
            "unit": unit,
            "success": False,
        }

        url = (
            "https://query1.finance.yahoo.com/"
            f"v8/finance/chart/{sym}"
            "?range=5d&interval=1d"
        )

        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": self.USER_AGENT,
                },
            )

            with urllib.request.urlopen(
                req,
                context=self.ssl_context,
                timeout=6,
            ) as resp:
                raw_json = json.loads(
                    resp.read().decode("utf-8")
                )

            res_list = (
                raw_json
                .get("chart", {})
                .get("result", [])
            )

            if not res_list:
                return default_result

            first = res_list[0]
            chart_meta = first.get("meta", {})

            current_price = float(
                chart_meta.get(
                    "regularMarketPrice",
                    0.0,
                )
                or 0.0
            )

            if current_price <= 0:
                return default_result

            closes: List[float] = []

            quotes = (
                first
                .get("indicators", {})
                .get("quote", [])
            )

            if quotes:
                raw_closes = quotes[0].get(
                    "close",
                    [],
                )

                closes = [
                    float(c)
                    for c in raw_closes
                    if c is not None
                ]

            reg_chg_pct = chart_meta.get(
                "regularMarketChangePercent"
            )

            full_chg = chart_meta.get(
                "regularMarketChange"
            )

            if full_chg is None:
                full_chg = chart_meta.get(
                    "fulldayChange"
                )

            if reg_chg_pct is not None:
                change_pct = float(reg_chg_pct)

                if full_chg is not None:
                    prev_close = (
                        current_price
                        - float(full_chg)
                    )

                elif change_pct != -100.0:
                    prev_close = (
                        current_price
                        / (
                            1.0
                            + change_pct / 100.0
                        )
                    )

                else:
                    prev_close = current_price

            else:
                prev_close = 0.0

                if len(closes) >= 2:
                    if (
                        abs(
                            current_price
                            - closes[-1]
                        )
                        / max(
                            current_price,
                            1e-6,
                        )
                        < 0.0005
                    ):
                        prev_close = closes[-2]
                    else:
                        prev_close = closes[-1]

                elif len(closes) == 1:
                    prev_close = closes[0]

                else:
                    prev_close = (
                        chart_meta.get(
                            "previousClose"
                        )
                        or chart_meta.get(
                            "chartPreviousClose"
                        )
                        or current_price
                    )

                change_pct = 0.0

                if prev_close > 0:
                    change_pct = (
                        (
                            current_price
                            - prev_close
                        )
                        / prev_close
                        * 100.0
                    )

            price_str = self._format_price(
                current_price,
                unit,
                decimals,
            )

            # ------------------------------------------------
            # 미국 10년물 국채금리
            # ------------------------------------------------
            # 금리의 움직임은 상대 변화율(%)보다
            # basis point(bp)로 표시하는 것이 명확합니다.
            #
            # 예:
            # 5.16% -> 5.18%
            # = +0.02%p
            # = +2bp
            # ------------------------------------------------

            if key == "us10y_yield":

                daily_change_bp = (
                    current_price
                    - prev_close
                ) * 100.0

                if daily_change_bp > 0:
                    change_str = (
                        f"+{daily_change_bp:.1f}bp"
                    )
                elif daily_change_bp < 0:
                    change_str = (
                        f"{daily_change_bp:.1f}bp"
                    )
                else:
                    change_str = "0.0bp"

                (
                    trend,
                    trend_badge,
                    five_d_bp,
                ) = self._calculate_yield_trend(
                    current_price,
                    closes,
                    daily_change_bp,
                )

                return {
                    "key": key,
                    "name": name,
                    "symbol": sym,
                    "price": current_price,
                    "price_str": price_str,

                    # 호환성을 위해 기존 change_pct는
                    # Yahoo의 상대 변화율 값을 유지합니다.
                    # 실제 리포트 표시는 change_str의 bp를 사용합니다.
                    "change_pct": round(
                        change_pct,
                        2,
                    ),

                    "change_str": change_str,
                    "change_bp": round(
                        daily_change_bp,
                        1,
                    ),

                    "trend": trend,
                    "trend_badge": trend_badge,

                    # 기존 필드와의 호환성을 위해 유지.
                    # 10년물의 실제 5일 변화는
                    # 5d_change_bp를 사용합니다.
                    "5d_change_pct": 0.0,
                    "5d_change_bp": round(
                        five_d_bp,
                        1,
                    ),

                    "unit": unit,
                    "success": True,
                }

            # ------------------------------------------------
            # 일반 시장지표
            # ------------------------------------------------

            (
                trend,
                trend_badge,
                five_d_pct,
            ) = self._calculate_trend(
                current_price,
                closes,
                change_pct,
            )

            sign = (
                "+"
                if change_pct > 0
                else ""
            )

            change_str = (
                f"{sign}{change_pct:.2f}%"
            )

            return {
                "key": key,
                "name": name,
                "symbol": sym,
                "price": current_price,
                "price_str": price_str,
                "change_pct": round(
                    change_pct,
                    2,
                ),
                "change_str": change_str,
                "trend": trend,
                "trend_badge": trend_badge,
                "5d_change_pct": round(
                    five_d_pct,
                    2,
                ),
                "5d_change_bp": None,
                "unit": unit,
                "success": True,
            }

        except Exception as e:
            logger.warning(
                "매크로 지표 [%s (%s)] 조회 실패: %s",
                name,
                sym,
                e,
            )

            return default_result

    # ========================================================
    # 공식 미국 경제지표
    # ========================================================

    def _fetch_us_economic_indicators(
        self,
    ) -> Dict[str, Any]:

        fundamentals = {
            "core_pce": self._empty_indicator(
                "미국 근원 PCE 물가지수"
            ),
            "jobs_nfp": self._empty_indicator(
                "미국 비농업 신규고용 (NFP)"
            ),
            "unemployment_rate": (
                self._empty_indicator(
                    "미국 실업률"
                )
            ),
        }

        # BEA 근원 PCE
        try:
            fundamentals["core_pce"] = (
                self._fetch_core_pce()
            )
        except Exception as e:
            logger.warning(
                "근원 PCE 조회 실패: %s",
                e,
            )

        # BLS 고용
        try:
            bls_data = self._fetch_bls_data()

            if bls_data.get("jobs_nfp"):
                fundamentals["jobs_nfp"] = (
                    bls_data["jobs_nfp"]
                )

            if bls_data.get(
                "unemployment_rate"
            ):
                fundamentals[
                    "unemployment_rate"
                ] = bls_data[
                    "unemployment_rate"
                ]

        except Exception as e:
            logger.warning(
                "BLS 고용지표 조회 실패: %s",
                e,
            )

        return fundamentals

    def _empty_indicator(
        self,
        name: str,
    ) -> Dict[str, Any]:

        return {
            "name": name,
            "latest_value": "조회 실패",
            "previous_value": "-",
            "change_text": "-",
            "trend": "UNKNOWN",
            "trend_badge": "데이터 없음",
            "period": "데이터 조회 실패",
            "description": (
                "공식 데이터 조회에 실패하여 "
                "투자 판단 근거에서 제외"
            ),
            "success": False,
        }

    # ========================================================
    # BEA 근원 PCE
    # ========================================================

    def _fetch_core_pce(
        self,
    ) -> Dict[str, Any]:
        """
        BEA NIPA Table 2.8.4(T20804)의
        Line 25 'PCE excluding food and energy' 가격지수를
        이용해 최신 월과 직전 월의 전년동월비(YoY)를
        직접 계산합니다.
        """

        api_key = os.getenv(
            "BEA_API_KEY",
            "",
        ).strip()

        if not api_key:
            raise RuntimeError(
                "BEA_API_KEY 환경변수가 "
                "설정되지 않았습니다."
            )

        today = datetime.date.today()

        # 연초에도 최신월/직전월의 YoY 계산이 가능하도록
        # 2년 전부터 금년까지 3개 연도를 요청합니다.
        years = (
            f"{today.year - 2},"
            f"{today.year - 1},"
            f"{today.year}"
        )

        params = {
            "UserID": api_key,
            "method": "GetData",
            "datasetname": "NIPA",
            "TableName": BEA_CORE_PCE_TABLE,
            "Frequency": "M",
            "Year": years,
            "ResultFormat": "JSON",
        }

        url = (
            BEA_API_URL
            + "?"
            + urllib.parse.urlencode(params)
        )

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.USER_AGENT,
            },
        )

        with urllib.request.urlopen(
            req,
            context=self.ssl_context,
            timeout=30,
        ) as resp:
            result = json.loads(
                resp.read().decode("utf-8")
            )

        bea_api = result.get(
            "BEAAPI",
            {},
        )

        results = bea_api.get(
            "Results",
            {},
        )

        error = (
            results.get("Error")
            or bea_api.get("Error")
        )

        if error:
            raise RuntimeError(
                "BEA API 오류: "
                + json.dumps(
                    error,
                    ensure_ascii=False,
                )
            )

        rows = results.get(
            "Data",
            [],
        )

        if not rows:
            raise RuntimeError(
                "BEA PCE 데이터가 비어 있습니다."
            )

        observations = []

        for row in rows:
            line_number = str(
                row.get(
                    "LineNumber",
                    "",
                )
            ).strip()

            description = str(
                row.get(
                    "LineDescription",
                    "",
                )
            ).strip()

            # Market-based PCE excluding food and energy
            # (Line 31)와 혼동하지 않도록
            # Line 25를 우선적으로 정확히 확인합니다.
            if (
                line_number
                != BEA_CORE_PCE_LINE_NUMBER
            ):
                continue

            if (
                description.lower()
                != BEA_CORE_PCE_DESCRIPTION.lower()
            ):
                logger.warning(
                    "BEA T20804 Line 25 설명이 "
                    "예상과 다릅니다: %s",
                    description,
                )
                continue

            period = str(
                row.get(
                    "TimePeriod",
                    "",
                )
            ).strip()

            value_text = str(
                row.get(
                    "DataValue",
                    "",
                )
            ).strip()

            parsed_period = (
                self._parse_bea_month(
                    period
                )
            )

            if parsed_period is None:
                continue

            try:
                value = float(
                    value_text.replace(
                        ",",
                        "",
                    )
                )
            except (
                ValueError,
                TypeError,
            ):
                continue

            if value <= 0:
                continue

            year, month = parsed_period

            observations.append(
                {
                    "year": year,
                    "month": month,
                    "value": value,
                }
            )

        observations.sort(
            key=lambda x: (
                x["year"],
                x["month"],
            )
        )

        if len(observations) < 14:
            raise RuntimeError(
                "BEA 근원 PCE 관측치가 "
                "충분하지 않습니다."
            )

        latest = observations[-1]
        previous = observations[-2]

        latest_year_ago = (
            self._find_bea_observation(
                observations,
                latest["year"] - 1,
                latest["month"],
            )
        )

        previous_year_ago = (
            self._find_bea_observation(
                observations,
                previous["year"] - 1,
                previous["month"],
            )
        )

        if (
            latest_year_ago is None
            or previous_year_ago is None
        ):
            raise RuntimeError(
                "BEA 근원 PCE의 "
                "전년동월 관측치를 "
                "찾지 못했습니다."
            )

        latest_yoy = (
            (
                latest["value"]
                / latest_year_ago
            )
            - 1.0
        ) * 100.0

        previous_yoy = (
            (
                previous["value"]
                / previous_year_ago
            )
            - 1.0
        ) * 100.0

        change = (
            latest_yoy
            - previous_yoy
        )

        (
            trend,
            trend_badge,
        ) = self._inflation_trend(
            change
        )

        return {
            "name": (
                "미국 근원 PCE 물가지수"
            ),
            "latest_value": (
                f"{latest_yoy:.1f}%"
            ),
            "previous_value": (
                f"{previous_yoy:.1f}%"
            ),
            "change_text": (
                "전월 발표 대비 "
                f"{change:+.1f}%p"
            ),
            "trend": trend,
            "trend_badge": trend_badge,
            "period": (
                f"{latest['year']}."
                f"{latest['month']:02d}월"
            ),
            "description": (
                "BEA NIPA Table 2.8.4 "
                "Line 25 근원 PCE 가격지수의 "
                "전년동월비 자동 계산"
            ),
            "source": (
                "U.S. Bureau of Economic Analysis"
            ),
            "success": True,
        }

    def _parse_bea_month(
        self,
        period: str,
    ) -> tuple[int, int] | None:
        """
        BEA 월별 TimePeriod 형식
        예: 2026M07
        """

        if (
            len(period) != 7
            or period[4] != "M"
        ):
            return None

        try:
            year = int(
                period[:4]
            )

            month = int(
                period[5:]
            )
        except ValueError:
            return None

        if not 1 <= month <= 12:
            return None

        return (
            year,
            month,
        )

    def _find_bea_observation(
        self,
        observations: List[Dict[str, Any]],
        year: int,
        month: int,
    ) -> float | None:

        for item in reversed(
            observations
        ):
            if (
                item["year"] == year
                and item["month"] == month
            ):
                return float(
                    item["value"]
                )

        return None

    def _inflation_trend(
        self,
        change: float,
    ) -> tuple[str, str]:

        if change <= -0.05:
            return (
                "DOWN",
                "▼ 물가 상승률 둔화",
            )

        if change >= 0.05:
            return (
                "UP",
                "▲ 물가 상승률 확대",
            )

        return (
            "FLAT",
            "━ 물가 상승률 보합",
        )

    # ========================================================
    # BLS NFP + 실업률
    # ========================================================

    def _fetch_bls_data(
        self,
    ) -> Dict[str, Any]:

        current_year = (
            datetime.date.today().year
        )

        payload = {
            "seriesid": [
                BLS_NFP_SERIES,
                BLS_UNEMPLOYMENT_SERIES,
            ],
            "startyear": str(
                current_year - 1
            ),
            "endyear": str(
                current_year
            ),
        }

        data = json.dumps(
            payload
        ).encode("utf-8")

        req = urllib.request.Request(
            BLS_API_URL,
            data=data,
            headers={
                "Content-Type": (
                    "application/json"
                ),
                "User-Agent": (
                    self.USER_AGENT
                ),
            },
            method="POST",
        )

        with urllib.request.urlopen(
            req,
            context=self.ssl_context,
            timeout=8,
        ) as resp:
            result = json.loads(
                resp.read().decode(
                    "utf-8"
                )
            )

        if (
            result.get("status")
            != "REQUEST_SUCCEEDED"
        ):
            raise RuntimeError(
                "BLS API 요청 실패"
            )

        series_list = (
            result
            .get("Results", {})
            .get("series", [])
        )

        series_map = {
            item.get("seriesID"): (
                item.get("data", [])
            )
            for item in series_list
        }

        nfp_rows = self._normalize_bls_rows(
            series_map.get(
                BLS_NFP_SERIES,
                [],
            )
        )

        unemployment_rows = (
            self._normalize_bls_rows(
                series_map.get(
                    BLS_UNEMPLOYMENT_SERIES,
                    [],
                )
            )
        )

        return {
            "jobs_nfp": (
                self._build_nfp_indicator(
                    nfp_rows
                )
            ),
            "unemployment_rate": (
                self._build_unemployment_indicator(
                    unemployment_rows
                )
            ),
        }

    def _normalize_bls_rows(
        self,
        rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:

        normalized = []

        for row in rows:
            period = str(
                row.get(
                    "period",
                    "",
                )
            )

            # M13 = 연평균이므로 제외
            if (
                not period.startswith("M")
                or period == "M13"
            ):
                continue

            try:
                month = int(
                    period[1:]
                )

                year = int(
                    row.get("year")
                )

                value = float(
                    row.get("value")
                )

            except (
                ValueError,
                TypeError,
            ):
                continue

            normalized.append(
                {
                    "year": year,
                    "month": month,
                    "value": value,
                }
            )

        normalized.sort(
            key=lambda x: (
                x["year"],
                x["month"],
            )
        )

        return normalized

    def _build_nfp_indicator(
        self,
        rows: List[Dict[str, Any]],
    ) -> Dict[str, Any]:

        if len(rows) < 3:
            return self._empty_indicator(
                "미국 비농업 신규고용 (NFP)"
            )

        latest = rows[-1]
        previous = rows[-2]
        before_previous = rows[-3]

        # CES0000000001은
        # 총 비농업 고용수준(천 명 단위).
        # 월간 차이를 신규고용으로 계산합니다.
        latest_change = (
            latest["value"]
            - previous["value"]
        )

        previous_change = (
            previous["value"]
            - before_previous["value"]
        )

        change_vs_previous = (
            latest_change
            - previous_change
        )

        if change_vs_previous >= 25:
            trend = "UP"
            trend_badge = (
                "▲ 고용 증가폭 확대"
            )

        elif change_vs_previous <= -25:
            trend = "DOWN"
            trend_badge = (
                "▼ 고용 증가폭 둔화"
            )

        else:
            trend = "FLAT"
            trend_badge = (
                "━ 고용 증가폭 유사"
            )

        return {
            "name": (
                "미국 비농업 신규고용 (NFP)"
            ),
            "latest_value": (
                f"{latest_change:+,.0f}K"
            ),
            "previous_value": (
                f"{previous_change:+,.0f}K"
            ),
            "change_text": (
                "직전월 증가폭 대비 "
                f"{change_vs_previous:+,.0f}K"
            ),
            "trend": trend,
            "trend_badge": trend_badge,
            "period": (
                f"{latest['year']}."
                f"{latest['month']:02d}월"
            ),
            "description": (
                "BLS 총 비농업 고용수준의 "
                "월간 증감 자동 계산"
            ),
            "source": (
                "U.S. Bureau of Labor Statistics"
            ),
            "success": True,
        }

    def _build_unemployment_indicator(
        self,
        rows: List[Dict[str, Any]],
    ) -> Dict[str, Any]:

        if len(rows) < 2:
            return self._empty_indicator(
                "미국 실업률"
            )

        latest = rows[-1]
        previous = rows[-2]

        latest_rate = latest["value"]
        previous_rate = previous["value"]

        change = (
            latest_rate
            - previous_rate
        )

        if change >= 0.05:
            trend = "UP"
            trend_badge = (
                "▲ 실업률 상승"
            )

        elif change <= -0.05:
            trend = "DOWN"
            trend_badge = (
                "▼ 실업률 하락"
            )

        else:
            trend = "FLAT"
            trend_badge = (
                "━ 실업률 보합"
            )

        return {
            "name": "미국 실업률",
            "latest_value": (
                f"{latest_rate:.1f}%"
            ),
            "previous_value": (
                f"{previous_rate:.1f}%"
            ),
            "change_text": (
                f"전월 대비 {change:+.1f}%p"
            ),
            "trend": trend,
            "trend_badge": trend_badge,
            "period": (
                f"{latest['year']}."
                f"{latest['month']:02d}월"
            ),
            "description": (
                "BLS 공식 실업률"
            ),
            "source": (
                "U.S. Bureau of Labor Statistics"
            ),
            "success": True,
        }

    # ========================================================
    # 시장 트렌드
    # ========================================================

    def _calculate_trend(
        self,
        current_price: float,
        closes: List[float],
        change_pct: float,
    ) -> tuple[str, str, float]:

        if (
            not closes
            or len(closes) < 2
        ):
            if change_pct >= 0.5:
                return (
                    "UP",
                    "▲ 상승 추세",
                    change_pct,
                )

            if change_pct <= -0.5:
                return (
                    "DOWN",
                    "▼ 하락 추세",
                    change_pct,
                )

            return (
                "FLAT",
                "━ 보합세",
                change_pct,
            )

        first_close = closes[0]
        last_close = closes[-1]

        five_d_pct = (
            (
                last_close
                - first_close
            )
            / first_close
            * 100.0
            if first_close > 0
            else 0.0
        )

        if five_d_pct >= 1.5:
            return (
                "UP",
                (
                    "▲ 강한 상승 "
                    f"(+{five_d_pct:.1f}%)"
                ),
                five_d_pct,
            )

        if five_d_pct >= 0.4:
            return (
                "UP",
                (
                    "▲ 상승 추세 "
                    f"(+{five_d_pct:.1f}%)"
                ),
                five_d_pct,
            )

        if five_d_pct <= -1.5:
            return (
                "DOWN",
                (
                    "▼ 하락 추세 "
                    f"({five_d_pct:.1f}%)"
                ),
                five_d_pct,
            )

        if five_d_pct <= -0.4:
            return (
                "DOWN",
                (
                    "▼ 완만한 하락 "
                    f"({five_d_pct:.1f}%)"
                ),
                five_d_pct,
            )

        return (
            "FLAT",
            (
                "━ 횡보/보합 "
                f"({five_d_pct:+.1f}%)"
            ),
            five_d_pct,
        )

    def _calculate_yield_trend(
        self,
        current_yield: float,
        closes: List[float],
        daily_change_bp: float,
    ) -> tuple[str, str, float]:
        """
        미국 국채금리 전용 추세 계산.

        주가지수처럼 상대 변화율(%)을 사용하지 않고
        금리 수준의 차이를 basis point(bp)로 계산합니다.
        """

        # 5일 데이터가 충분하지 않은 경우
        # 당일 변화만으로 방향을 판단합니다.
        if (
            not closes
            or len(closes) < 2
        ):
            if daily_change_bp >= 5.0:
                return (
                    "UP",
                    (
                        "▲ 금리 상승 "
                        f"(당일 +{daily_change_bp:.1f}bp)"
                    ),
                    daily_change_bp,
                )

            if daily_change_bp <= -5.0:
                return (
                    "DOWN",
                    (
                        "▼ 금리 하락 "
                        f"(당일 {daily_change_bp:.1f}bp)"
                    ),
                    daily_change_bp,
                )

            return (
                "FLAT",
                (
                    "━ 금리 보합 "
                    f"(당일 {daily_change_bp:+.1f}bp)"
                ),
                daily_change_bp,
            )

        first_yield = closes[0]

        # Yahoo의 마지막 close가 현재가와 사실상 동일하면
        # 그대로 사용합니다.
        # 장중 데이터 등으로 차이가 있을 경우에는
        # 현재 regularMarketPrice를 최신값으로 사용합니다.
        last_yield = current_yield

        five_d_bp = (
            last_yield
            - first_yield
        ) * 100.0

        # 5거래일 기준 ±10bp 이상이면
        # 의미 있는 금리 방향성으로 판단합니다.
        if five_d_bp >= 10.0:
            return (
                "UP",
                (
                    "▲ 금리 상승 "
                    f"(5일 +{five_d_bp:.1f}bp)"
                ),
                five_d_bp,
            )

        if five_d_bp <= -10.0:
            return (
                "DOWN",
                (
                    "▼ 금리 하락 "
                    f"(5일 {five_d_bp:.1f}bp)"
                ),
                five_d_bp,
            )

        return (
            "FLAT",
            (
                "━ 금리 보합 "
                f"(5일 {five_d_bp:+.1f}bp)"
            ),
            five_d_bp,
        )
      

    # ========================================================
    # 가격 포맷
    # ========================================================

    def _format_price(
        self,
        price: float,
        unit: str,
        decimals: int,
    ) -> str:

        if unit == "원":
            return f"{price:,.1f}원"

        if unit == "$":
            return f"${price:,.2f}"

        if unit == "%":
            return f"{price:.2f}%"

        if decimals == 0:
            return (
                f"{price:,.0f} {unit}"
            )

        return (
            f"{price:,.{decimals}f} {unit}"
        )

    # ========================================================
    # Gemini용 요약
    # ========================================================

    def build_summary_for_gemini(
        self,
        macro_data: Dict[str, Any],
    ) -> str:

        raw = macro_data.get(
            "raw_items",
            {},
        )

        fund = macro_data.get(
            "fundamentals",
            {},
        )

        lines = [
            (
                "[글로벌 거시경제 지표 및 "
                "최근 트렌드]"
            ),
            "1. 미국 3대 증시:",
            (
                "  - S&P 500: "
                f"{raw.get('sp500', {}).get('price_str', '-')} "
                f"({raw.get('sp500', {}).get('change_str', '-')}) "
                f"[{raw.get('sp500', {}).get('trend_badge', '-')}]"
            ),
            (
                "  - Nasdaq 100: "
                f"{raw.get('nasdaq100', {}).get('price_str', '-')} "
                f"({raw.get('nasdaq100', {}).get('change_str', '-')}) "
                f"[{raw.get('nasdaq100', {}).get('trend_badge', '-')}]"
            ),
            (
                "  - Dow Jones: "
                f"{raw.get('dow', {}).get('price_str', '-')} "
                f"({raw.get('dow', {}).get('change_str', '-')}) "
                f"[{raw.get('dow', {}).get('trend_badge', '-')}]"
            ),
            "2. 국내 2대 증시:",
            (
                "  - 코스피 (KOSPI): "
                f"{raw.get('kospi', {}).get('price_str', '-')} "
                f"({raw.get('kospi', {}).get('change_str', '-')}) "
                f"[{raw.get('kospi', {}).get('trend_badge', '-')}]"
            ),
            (
                "  - 코스닥 (KOSDAQ): "
                f"{raw.get('kosdaq', {}).get('price_str', '-')} "
                f"({raw.get('kosdaq', {}).get('change_str', '-')}) "
                f"[{raw.get('kosdaq', {}).get('trend_badge', '-')}]"
            ),
            "3. 환율·유가·국채금리:",
            (
                "  - 원/달러 환율: "
                f"{raw.get('usd_krw', {}).get('price_str', '-')} "
                f"({raw.get('usd_krw', {}).get('change_str', '-')}) "
                f"[{raw.get('usd_krw', {}).get('trend_badge', '-')}]"
            ),
            (
                "  - WTI 국제유가: "
                f"{raw.get('wti_oil', {}).get('price_str', '-')} "
                f"({raw.get('wti_oil', {}).get('change_str', '-')}) "
                f"[{raw.get('wti_oil', {}).get('trend_badge', '-')}]"
            ),
            (
                "  - 미국 10년물 국채금리: "
                f"{raw.get('us10y_yield', {}).get('price_str', '-')} "
                f"({raw.get('us10y_yield', {}).get('change_str', '-')}) "
                f"[{raw.get('us10y_yield', {}).get('trend_badge', '-')}]"
            ),
            "4. 미국 공식 경제지표:",
            self._fundamental_summary_line(
                "근원 PCE",
                fund.get(
                    "core_pce",
                    {},
                ),
            ),
            self._fundamental_summary_line(
                "비농업 신규고용 (NFP)",
                fund.get(
                    "jobs_nfp",
                    {},
                ),
            ),
            self._fundamental_summary_line(
                "미국 실업률",
                fund.get(
                    "unemployment_rate",
                    {},
                ),
            ),
            (
                "※ '데이터 없음' 또는 '조회 실패'로 "
                "표시된 지표는 투자 판단 근거로 "
                "사용하지 마세요."
            ),
        ]

        return "\n".join(lines)

    def _fundamental_summary_line(
        self,
        label: str,
        data: Dict[str, Any],
    ) -> str:

        if not data.get("success"):
            return (
                f"  - {label}: 데이터 조회 실패 "
                "[투자 판단에서 제외]"
            )

        return (
            f"  - {label}: "
            f"{data.get('latest_value', '-')} "
            f"[{data.get('trend_badge', '-')}] "
            f"(기준: {data.get('period', '-')})"
        )

    # ========================================================
    # Kakao용 요약
    # ========================================================

    def build_kakao_macro_lines(
        self,
        macro_data: Dict[str, Any],
    ) -> List[str]:

        raw = macro_data.get(
            "raw_items",
            {},
        )

        fund = macro_data.get(
            "fundamentals",
            {},
        )

        sp = raw.get("sp500", {})
        ndx = raw.get("nasdaq100", {})
        kospi = raw.get("kospi", {})
        usd = raw.get("usd_krw", {})
        oil = raw.get("wti_oil", {})
        tnx = raw.get("us10y_yield", {})

        pce = fund.get(
            "core_pce",
            {},
        )

        job = fund.get(
            "jobs_nfp",
            {},
        )

        unemployment = fund.get(
            "unemployment_rate",
            {},
        )

        pce_text = (
            pce.get("latest_value")
            if pce.get("success")
            else "조회 실패"
        )

        job_text = (
            job.get("latest_value")
            if job.get("success")
            else "조회 실패"
        )

        unemployment_text = (
            unemployment.get("latest_value")
            if unemployment.get("success")
            else "조회 실패"
        )

        lines = [
            "📊 글로벌 주요 지표 & 최근 트렌드:",
            (
                "• 美증시: "
                f"S&P {sp.get('price', 0):,.0f}"
                f"({sp.get('change_str', '')}) / "
                f"나스닥 {ndx.get('price', 0):,.0f}"
                f"({ndx.get('change_str', '')})"
            ),
            (
                "• 韓증시: "
                f"코스피 {kospi.get('price', 0):,.0f}"
                f"({kospi.get('change_str', '')}) "
                f"[{kospi.get('trend_badge', '')}]"
            ),
            (
                "• 거시: "
                f"환율 {usd.get('price', 0):,.1f}원 / "
                f"10년금리 {tnx.get('price', 0):.2f}% / "
                f"유가 {oil.get('price', 0):.1f}$"
            ),
            (
                "• 경제: "
                f"근원PCE {pce_text} / "
                f"NFP {job_text} / "
                f"실업률 {unemployment_text}"
            ),
        ]

        return lines
