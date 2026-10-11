"""Read-only, explainable equity screening. Educational research, not trade advice.

Uses Yahoo Finance fundamentals when available; missing metrics never score as zero.
Universe is a curated sample, not all listed stocks.
"""
from datetime import datetime, timezone
import math
import time

UNIVERSE = {
    "us": {
        "technology": ["MSFT", "AAPL", "CSCO", "ORCL"],
        "financials": ["JPM", "BAC", "WFC", "C"],
        "healthcare": ["JNJ", "MRK", "ABBV", "PFE"],
        "industrials": ["CAT", "DE", "HON", "GE"],
        "consumer_discretionary": ["AMZN", "HD", "MCD", "NKE"],
        "consumer_staples": ["PG", "KO", "PEP", "WMT"],
        "energy": ["XOM", "CVX", "COP", "SLB"],
        "utilities": ["NEE", "SO", "DUK", "AEP"],
        "materials": ["LIN", "SHW", "ECL", "NEM"],
        "real_estate": ["PLD", "AMT", "EQIX", "O"],
        "communication": ["GOOGL", "META", "VZ", "T"],
    },
    "kr": {
        "semiconductors": ["005930.KS", "000660.KS"],
        "banks": ["105560.KS", "055550.KS", "086790.KS"],
        "automobiles": ["005380.KS", "000270.KS"],
        "healthcare": ["207940.KS", "068270.KS"],
    },
}
CACHE = {}
TTL_SECONDS = 1800
FIELDS = ("trailingPE", "forwardPE", "priceToBook", "returnOnEquity",
          "revenueGrowth", "earningsGrowth", "profitMargins", "fiftyTwoWeekChange")


def _finite(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _fetch_info(ticker):
    import yfinance as yf
    return yf.Ticker(ticker).info or {}


def _score(info):
    """Absolute screening heuristics, with an explicit coverage requirement."""
    pe = _finite(info.get("forwardPE"))
    if pe is None or pe <= 0:
        pe = _finite(info.get("trailingPE"))
    pb = _finite(info.get("priceToBook"))
    roe = _finite(info.get("returnOnEquity"))
    growth = _finite(info.get("revenueGrowth"))
    margin = _finite(info.get("profitMargins"))
    momentum = _finite(info.get("fiftyTwoWeekChange"))
    metrics = {"pe": pe, "pb": pb, "roe": roe, "revenue_growth": growth,
               "profit_margin": margin, "year_change": momentum}
    checks = {
        "reasonable_pe": None if pe is None else 0 < pe <= 20,
        "reasonable_pb": None if pb is None else 0 < pb <= 3,
        "positive_roe": None if roe is None else roe >= .10,
        "revenue_growth": None if growth is None else growth >= .05,
        "profitable": None if margin is None else margin > 0,
        "price_momentum": None if momentum is None else momentum >= 0,
    }
    available = [value for value in checks.values() if value is not None]
    return {
        "metrics": metrics, "checks": checks,
        "coverage": len(available), "total_metrics": len(checks),
        "score": round(100 * sum(available) / len(available), 1) if available else None,
        "eligible": len(available) >= 4,
    }


def screen_sector(market, sector):
    if market not in UNIVERSE or sector not in UNIVERSE[market]:
        raise ValueError("지원하지 않는 시장 또는 섹터입니다.")
    key = (market, sector)
    cached = CACHE.get(key)
    if cached and time.monotonic() - cached[0] < TTL_SECONDS:
        return cached[1]
    results, failures = [], {}
    for ticker in UNIVERSE[market][sector]:
        try:
            info = _fetch_info(ticker)
            if not isinstance(info, dict) or not info:
                raise ValueError("기업 정보 없음")
            assessment = _score(info)
            results.append({
                "ticker": ticker,
                "name": str(info.get("shortName") or ticker)[:120],
                "currency": str(info.get("currency") or ""),
                **assessment,
            })
        except Exception:
            failures[ticker] = "기업 정보 조회 실패"
    results.sort(key=lambda item: (
        not item["eligible"],
        -(item["score"] if item["score"] is not None else -1),
        item["ticker"],
    ))
    result = {
        "market": market, "sector": sector, "as_of": datetime.now(timezone.utc).isoformat(),
        "sample_size": len(UNIVERSE[market][sector]),
        "results": results, "failures": failures,
        "method": "동일 가중 6개 휴리스틱(PE, PBR, ROE, 매출성장, 순이익률, 52주 가격변화); 4개 이상 관측 시 평가 가능",
        "disclaimer": "제한된 표본의 정량 선별 결과이며 저평가 확정 또는 매수 추천이 아닙니다. 업종별 적정 PER/PBR이 달라 직접 비교에 주의하세요.",
    }
    CACHE[key] = (time.monotonic(), result)
    return result
