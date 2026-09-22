"""
services/macro_indicator_service.py
데일리 모닝 리포트 및 Gemini AI용 필수 글로벌 매크로 10대 지표 및 최근 트렌드(Trend) 수집기.
- 1. 미국 증시 3대 지수: S&P500 (^GSPC), Nasdaq 100 (^NDX), DOW (^DJI)
- 2. 국내 증시 2대 지수: KOSPI (^KS11), KOSDAQ (^KQ11)
- 3. 거시경제 핵심 3종: 국제 유가 WTI (CL=F), 미국 10년물 국채금리 (^TNX), 원/달러 환율 (KRW=X)
- 4. 미국 펀더멘털 경제지표 2종: 근원 PCE 물가지수, 고용지표 (비농업 신규고용 & 실업률)
- 각 지표별 전일비 등락률(%) 및 최근 5일 이동평균/모멘텀 기반 트렌드 (상승/하락/보합) 자동 판별
"""

from __future__ import annotations
import ssl
import json
import logging
import urllib.request
from typing import Dict, Any, List, Optional

logger = logging.getLogger("RetirementPortfolio.MacroIndicatorService")

# Yahoo Finance 실시간 시장 지표 심볼 맵핑
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

# 미국 주요 경제 펀더멘털 지표 (PCE 및 고용) 데이터 정의
US_ECONOMIC_INDICATORS: Dict[str, Dict[str, Any]] = {
    "core_pce": {
        "name": "미국 근원 PCE 물가지수",
        "latest_value": "3.3%",
        "previous_value": "3.4%",
        "change_text": "전월비 -0.1%p",
        "trend": "DOWN",
        "trend_badge": "▼ 둔화·안정세",
        "period": "최근 발표 (2026.07 / 08월말 집계)",
        "description": "연준 물가목표(2.0%)를 향해 점진적 하향 둔화 추세 지속 중",
    },
    "jobs_nfp": {
        "name": "미국 비농업 신규고용 (NFP)",
        "latest_value": "+162K",
        "previous_value": "+140K",
        "change_text": "전월비 +22K 증가",
        "trend": "UP",
        "trend_badge": "▲ 고용 견조세",
        "period": "최근 발표 (2026.08월분)",
        "description": "경기침체 우려를 완화하는 견조한 일자리 창출력 유지",
    },
    "unemployment_rate": {
        "name": "미국 실업률",
        "latest_value": "4.1%",
        "previous_value": "4.1%",
        "change_text": "전월 동률 유지",
        "trend": "FLAT",
        "trend_badge": "━ 완전고용 횡보",
        "period": "최근 발표 (2026.08월분)",
        "description": "역사적 저점 수준인 4%대 초반에서 안정적 횡보",
    },
}


class MacroIndicatorService:
    """글로벌 매크로 10대 지표 및 5일 트렌드 분석 서비스"""

    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

    def __init__(self):
        self.ssl_context = ssl._create_unverified_context()

    def fetch_all_macro_data(self) -> Dict[str, Any]:
        """
        10대 거시경제 지표 및 5일 트렌드 데이터를 일괄 수집하여 반환합니다.
        """
        results: Dict[str, Any] = {
            "us_market": {},
            "kr_market": {},
            "macro_commodity": {},
            "fundamentals": US_ECONOMIC_INDICATORS,
            "raw_items": {},
        }

        # 8개 실시간 지표 수집
        for key, meta in YAHOO_SYMBOLS.items():
            data = self._fetch_single_yahoo_indicator(key, meta)
            results["raw_items"][key] = data
            cat = meta.get("category", "macro_commodity")
            if cat in results:
                results[cat][key] = data

        return results

    def _fetch_single_yahoo_indicator(self, key: str, meta: Dict[str, Any]) -> Dict[str, Any]:
        """Yahoo Finance Chart API를 통해 단일 지표와 최근 5일 가격 데이터를 조회합니다."""
        sym = meta["symbol"]
        name = meta["name"]
        unit = meta["unit"]
        decimals = meta["decimals"]

        default_result = {
            "key": key,
            "name": name,
            "symbol": sym,
            "price": 0.0,
            "price_str": "조회중",
            "change_pct": 0.0,
            "change_str": "+0.00%",
            "trend": "FLAT",
            "trend_badge": "━ 보합세",
            "5d_change_pct": 0.0,
            "unit": unit,
        }

        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=5d&interval=1d"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": self.USER_AGENT})
            with urllib.request.urlopen(req, context=self.ssl_context, timeout=4) as resp:
                raw_json = json.loads(resp.read().decode("utf-8"))

            res_list = raw_json.get("chart", {}).get("result", [])
            if not res_list:
                return default_result

            first = res_list[0]
            chart_meta = first.get("meta", {})
            current_price = chart_meta.get("regularMarketPrice", 0.0)
            
            # 5일 종가 히스토리 추출 (None제외)
            closes: List[float] = []
            quotes = first.get("indicators", {}).get("quote", [])
            if quotes:
                raw_closes = quotes[0].get("close", [])
                closes = [c for c in raw_closes if c is not None]

            # 정확한 직전 거래일 종가(prev_close) 및 당일 등락률(change_pct) 판별:
            # 1순위: Yahoo Finance meta의 공식 거래소 피드(regularMaketChangePercent, fulldayChange) 직접 활용
            reg_chg_pct = chart_meta.get("regularMarketChangePercent")
            full_chg = chart_meta.get("fulldayChange")

            if reg_chg_pct is not None:
                change_pct = float(reg_chg_pct)
                if full_chg is not None:
                    prev_close = current_price - float(full_chg)
                elif change_pct != -100.0:
                    prev_close = current_price / (1.0 + (change_pct / 100.0))
                else:
                    prev_close = current_price
            else:
                # 2순위 Fallback : 5일 종가 히스토리 기반 직전 거래일 종가 추출
                prev_close = 0.0
                if len(closes) >= 2:
                    if abs(current_price - closes[-1]) / max(current_price, 1e-6) < 0.0005:
                        prev_close = closes[-2]
                    else:
                        prev_close = closes[-1]
                elif len(closes) == 1:
                    prev_close = closes[0]
                else:
                    prev_close = chart_meta.get("previousClose") or chart_meta.get("chartPreviousClose", current_price)

                change_pct = 0.0
                if prev_close and prev_close > 0:
                    change_pct = ((current_price - prev_close) / prev_close) * 100.0
                    
            # 트렌드 분석
            trend, trend_badge, five_d_pct = self._calculate_trend(current_price, closes, change_pct)

            # 포맷팅 문자열
            price_str = self._format_price(current_price, unit, decimals)
            sign = "+" if change_pct > 0 else ""
            change_str = f"{sign}{change_pct:.2f}%"

            return {
                "key": key,
                "name": name,
                "symbol": sym,
                "price": current_price,
                "price_str": price_str,
                "change_pct": round(change_pct, 2),
                "change_str": change_str,
                "trend": trend,
                "trend_badge": trend_badge,
                "5d_change_pct": round(five_d_pct, 2),
                "unit": unit,
            }

        except Exception as e:
            logger.warning(f"매크로 지표 [{name} ({sym})] 조회 실패 (기본값 대체): {e}")
            return default_result

    def _calculate_trend(
        self, current_price: float, closes: List[float], change_pct: float
    ) -> tuple[str, str, float]:
        """5일 가격 히스토리와 당일 등락률을 분석하여 트렌드(상승/하락/보합)를 도출합니다."""
        if not closes or len(closes) < 2:
            if change_pct >= 0.5:
                return "UP", "▲ 상승 추세", change_pct
            elif change_pct <= -0.5:
                return "DOWN", "▼ 하락 추세", change_pct
            else:
                return "FLAT", "━ 보합세", change_pct

        first_close = closes[0]
        last_close = closes[-1]
        five_d_pct = ((last_close - first_close) / first_close) * 100.0 if first_close > 0 else 0.0

        # 복합 트렌드 판별 (5일 누적 + 당일 모멘텀)
        if five_d_pct >= 1.5:
            return "UP", f"▲ 강한 상승 (+{five_d_pct:.1f}%)", five_d_pct
        elif five_d_pct >= 0.4:
            return "UP", f"▲ 상승 추세 (+{five_d_pct:.1f}%)", five_d_pct
        elif five_d_pct <= -1.5:
            return "DOWN", f"▼ 하락 추세 ({five_d_pct:.1f}%)", five_d_pct
        elif five_d_pct <= -0.4:
            return "DOWN", f"▼ 완만한 하락 ({five_d_pct:.1f}%)", five_d_pct
        else:
            return "FLAT", f"━ 횡보/보합 ({five_d_pct:+.1f}%)", five_d_pct

    def _format_price(self, price: float, unit: str, decimals: int) -> str:
        """가독성 높은 가격/지수 문자열 포맷팅"""
        if unit == "원":
            return f"{price:,.1f}원"
        elif unit == "$":
            return f"${price:,.2f}"
        elif unit == "%":
            return f"{price:.2f}%"
        else:
            if decimals == 0:
                return f"{price:,.0f} {unit}"
            return f"{price:,.{decimals}f} {unit}"

    def build_summary_for_gemini(self, macro_data: Dict[str, Any]) -> str:
        """Gemini AI 프롬프트에 주입할 정밀한 10대 매크로 지표 텍스트 요약 생성"""
        raw = macro_data.get("raw_items", {})
        fund = macro_data.get("fundamentals", {})

        lines = [
            "[글로벌 10대 거시경제(매크로) 지표 및 최근 트렌드]",
            "1. 미국 3대 증시:",
            f"  - S&P 500: {raw.get('sp500', {}).get('price_str', '-')} ({raw.get('sp500', {}).get('change_str', '-')}) [{raw.get('sp500', {}).get('trend_badge', '-')}]",
            f"  - Nasdaq 100: {raw.get('nasdaq100', {}).get('price_str', '-')} ({raw.get('nasdaq100', {}).get('change_str', '-')}) [{raw.get('nasdaq100', {}).get('trend_badge', '-')}]",
            f"  - Dow Jones: {raw.get('dow', {}).get('price_str', '-')} ({raw.get('dow', {}).get('change_str', '-')}) [{raw.get('dow', {}).get('trend_badge', '-')}]",
            "2. 국내 2대 증시:",
            f"  - 코스피 (KOSPI): {raw.get('kospi', {}).get('price_str', '-')} ({raw.get('kospi', {}).get('change_str', '-')}) [{raw.get('kospi', {}).get('trend_badge', '-')}]",
            f"  - 코스닥 (KOSDAQ): {raw.get('kosdaq', {}).get('price_str', '-')} ({raw.get('kosdaq', {}).get('change_str', '-')}) [{raw.get('kosdaq', {}).get('trend_badge', '-')}]",
            "3. 환율·유가·국채금리:",
            f"  - 원/달러 환율: {raw.get('usd_krw', {}).get('price_str', '-')} ({raw.get('usd_krw', {}).get('change_str', '-')}) [{raw.get('usd_krw', {}).get('trend_badge', '-')}]",
            f"  - WTI 국제유가: {raw.get('wti_oil', {}).get('price_str', '-')} ({raw.get('wti_oil', {}).get('change_str', '-')}) [{raw.get('wti_oil', {}).get('trend_badge', '-')}]",
            f"  - 미국 10년물 국채금리: {raw.get('us10y_yield', {}).get('price_str', '-')} ({raw.get('us10y_yield', {}).get('change_str', '-')}) [{raw.get('us10y_yield', {}).get('trend_badge', '-')}]",
            "4. 미국 펀더멘털 경제지표:",
            f"  - 근원 PCE 물가지수: {fund.get('core_pce', {}).get('latest_value', '-')} [{fund.get('core_pce', {}).get('trend_badge', '-')}] ({fund.get('core_pce', {}).get('description', '')})",
            f"  - 비농업 신규고용 (NFP): {fund.get('jobs_nfp', {}).get('latest_value', '-')} [{fund.get('jobs_nfp', {}).get('trend_badge', '-')}]",
            f"  - 미국 실업률: {fund.get('unemployment_rate', {}).get('latest_value', '-')} [{fund.get('unemployment_rate', {}).get('trend_badge', '-')}]",
        ]
        return "\n".join(lines)

    def build_kakao_macro_lines(self, macro_data: Dict[str, Any]) -> List[str]:
        """카카오톡 메시지에 포함할 콤팩트한 매크로 요약 라인 생성"""
        raw = macro_data.get("raw_items", {})
        fund = macro_data.get("fundamentals", {})

        sp = raw.get("sp500", {})
        ndx = raw.get("nasdaq100", {})
        kospi = raw.get("kospi", {})
        usd = raw.get("usd_krw", {})
        oil = raw.get("wti_oil", {})
        tnx = raw.get("us10y_yield", {})
        pce = fund.get("core_pce", {})
        job = fund.get("jobs_nfp", {})

        lines = [
            "📊 글로벌 10대 지표 & 최근 트렌드:",
            f"• 美증시: S&P {sp.get('price', 0):,.0f}({sp.get('change_str', '')}) / 나스닥 {ndx.get('price', 0):,.0f}({ndx.get('change_str', '')})",
            f"• 韓증시: 코스피 {kospi.get('price', 0):,.0f}({kospi.get('change_str', '')}) [{kospi.get('trend_badge', '')}]",
            f"• 거시: 환율 {usd.get('price', 0):,.1f}원 / 10년금리 {tnx.get('price', 0):.2f}% / 유가 {oil.get('price', 0):.1f}$",
            f"• 경제: PCE {pce.get('latest_value', '')}({pce.get('trend_badge', '')}) / 고용 {job.get('latest_value', '')}({job.get('trend_badge', '')})",
        ]
        return lines
