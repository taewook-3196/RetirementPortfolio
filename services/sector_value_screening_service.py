"""Read-only, explainable equity screening. Educational research, not trade advice.

Uses Yahoo Finance fundamentals when available; missing metrics never score as zero.
Universe is a curated sample, not all listed stocks.
"""
from datetime import datetime, timezone
import math
import statistics
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


def _score(info, sector_pe_median=None):
    """Sector-relative PE screening with an explicit coverage requirement."""
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
        "reasonable_pe": None if pe is None or sector_pe_median is None else 0 < pe <= sector_pe_median,
        "reasonable_pb": None if pb is None else 0 < pb <= 3,
        "positive_roe": None if roe is None else roe >= .10,
        "revenue_growth": None if growth is None else growth >= .05,
        "profitable": None if margin is None else margin > 0,
        "price_momentum": None if momentum is None else momentum >= 0,
    }
    available = [value for value in checks.values() if value is not None]
    return {
        "metrics": {**metrics, "sector_pe_median": sector_pe_median,
                    "pe_discount_pct": round((1 - pe / sector_pe_median) * 100, 2)
                    if pe is not None and pe > 0 and sector_pe_median else None},
        "checks": checks,
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
    results, failures, records = [], {}, []
    for ticker in UNIVERSE[market][sector]:
        try:
            info = _fetch_info(ticker)
            if not isinstance(info, dict) or not info:
                raise ValueError("기업 정보 없음")
            records.append((ticker, info))
        except Exception:
            failures[ticker] = "기업 정보 조회 실패"
    # Curated sample: never claim an industry-wide benchmark. Require 5
    # comparable positive forward PEs before allowing valuation labels.
    valid_pe = []
    for _, info in records:
        pe = _finite(info.get("forwardPE"))
        if pe is not None and 0 < pe <= 200:
            valid_pe.append(pe)
    sector_pe_median = statistics.median(valid_pe) if len(valid_pe) >= 5 else None
    sector_pe_mean = statistics.mean(valid_pe) if len(valid_pe) >= 3 else None
    for ticker, info in records:
        assessment = _score(info, sector_pe_median)
        # Valuation and investability are distinct: a low multiple is not
        # evidence of undervaluation without earnings quality and growth.
        discount = assessment["metrics"]["pe_discount_pct"]
        growth = assessment["metrics"]["revenue_growth"]
        roe = assessment["metrics"]["roe"]
        margin = assessment["metrics"]["profit_margin"]
        healthy = all(value is not None for value in (growth, roe, margin)) and growth >= 0 and roe > 0 and margin > 0
        if discount is None or not healthy:
            valuation = "평가 보류"
        elif discount >= 20:
            valuation = "상대 저평가 후보"
        elif discount >= 10:
            valuation = "다소 저평가 후보"
        elif discount >= -10:
            valuation = "상대 적정"
        elif discount >= -20:
            valuation = "다소 고평가 가능성"
        else:
            valuation = "상대 고평가 가능성"
        results.append({
            "valuation_label": valuation,
            "valuation_basis": "표본 Forward PER 및 최소 성장·수익성 검증",
            "ticker": ticker,
            "name": str(info.get("shortName") or ticker)[:120],
            "currency": str(info.get("currency") or ""),
            **assessment,
        })
    results.sort(key=lambda item: (
        not item["eligible"],
        -(item["score"] if item["score"] is not None else -1),
        item["ticker"],
    ))
    result = {
        "market": market, "sector": sector, "as_of": datetime.now(timezone.utc).isoformat(),
        "sample_size": len(UNIVERSE[market][sector]),
        "results": results, "failures": failures,
        "pe_benchmark": {"type": "curated_sample", "median": sector_pe_median,
                         "mean": round(sector_pe_mean, 2) if sector_pe_mean is not None else None,
                         "valid_count": len(valid_pe), "minimum_count": 5},
        "method": "임시 탐색 점수(6개 지표). PER 상대평가는 Forward PER 유효 표본 5개 이상인 경우만 사용. 가치평가와 투자매력도는 별개입니다.",
        "disclaimer": "제한된 표본의 정량 선별 결과이며 저평가 확정 또는 매수 추천이 아닙니다. PER 기준은 소규모 표본 중앙값이며 섹터 전체 평균이 아닙니다. 표본이 부족하면 가치평가를 보류합니다. 업종별 적정 PER/PBR이 달라 직접 비교에 주의하세요.",
    }
    CACHE[key] = (time.monotonic(), result)
    return result
