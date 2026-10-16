"""Read-only, explainable equity screening. Educational research, not trade advice.

Uses Yahoo Finance fundamentals when available; missing metrics never score as zero.
Universe is a curated sample, not all listed stocks.
"""
from datetime import datetime, timezone
import math
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

UNIVERSE = {
    "us": {
        "technology": ["MSFT", "AAPL", "CSCO", "ORCL", "ADBE", "CRM", "INTU", "IBM", "ACN", "NOW", "PANW", "SNPS"],
        "financials": ["JPM", "BAC", "WFC", "C", "GS", "MS", "USB", "PNC", "TFC", "BK", "SCHW", "AXP"],
        "healthcare": ["JNJ", "MRK", "ABBV", "PFE", "LLY", "UNH", "ABT", "TMO", "DHR", "BMY", "AMGN", "GILD"],
        "industrials": ["CAT", "DE", "HON", "GE", "RTX", "LMT", "ETN", "EMR", "UPS", "UNP", "WM", "PH"],
        "consumer_discretionary": ["AMZN", "HD", "MCD", "NKE", "LOW", "SBUX", "TJX", "BKNG", "CMG", "YUM", "ROST", "MAR"],
        "consumer_staples": ["PG", "KO", "PEP", "WMT", "COST", "CL", "KMB", "MDLZ", "GIS", "KHC", "HSY", "KR"],
        "energy": ["XOM", "CVX", "COP", "SLB", "EOG", "OXY", "MPC", "PSX", "VLO", "HAL", "DVN", "BKR"],
        "utilities": ["NEE", "SO", "DUK", "AEP", "D", "EXC", "SRE", "XEL", "ED", "WEC", "PEG", "EIX"],
        "materials": ["LIN", "SHW", "ECL", "NEM", "APD", "FCX", "NUE", "DOW", "DD", "VMC", "MLM", "PPG"],
        "real_estate": ["PLD", "AMT", "EQIX", "O", "WELL", "SPG", "DLR", "PSA", "VICI", "AVB", "EQR", "IRM"],
        "communication": ["GOOGL", "META", "VZ", "T", "NFLX", "DIS", "CMCSA", "TMUS", "CHTR", "EA", "TTWO", "OMC"],
    },
    "kr": {
        "semiconductors": ["005930.KS", "000660.KS", "042700.KS", "058470.KQ", "403870.KQ", "240810.KQ", "039030.KQ", "036930.KQ", "095340.KQ", "000990.KS"],
        "banks": ["105560.KS", "055550.KS", "086790.KS", "024110.KS", "316140.KS", "138930.KS", "175330.KS", "323410.KS", "139130.KS", "006220.KS"],
        "automobiles": ["005380.KS", "000270.KS", "012330.KS", "018880.KS", "011210.KS", "204320.KS", "064960.KS", "003620.KS", "161390.KS", "009900.KS"],
        "healthcare": ["207940.KS", "068270.KS", "128940.KS", "000100.KS", "326030.KS", "196170.KQ", "145020.KQ", "302440.KS", "091990.KQ", "141080.KQ"],
    },
}
# Sector-specific primary metrics; unsupported financial inputs trigger review.
SECTOR_POLICIES = {
    "financials": {"primary": "pbr_roe", "automatic_valuation": False},
    "banks": {"primary": "pbr_roe", "automatic_valuation": False},
    "real_estate": {"primary": "p_affo", "automatic_valuation": False},
    "semiconductors": {"primary": "normalized_earnings", "automatic_valuation": False},
}
DEFAULT_POLICY = {"primary": "forward_pe", "automatic_valuation": True}

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
    try:
        info = yf.Ticker(ticker).info or {}
        if any(_finite(info.get(field)) is not None for field in FIELDS):
            return info
    except Exception:
        info = {}
    # Annual SEC figures do not replace forecasts or live prices.
    if not ticker.endswith((".KS", ".KQ")):
        from services.sec_edgar_fundamentals import fetch_sec_fundamentals
        fundamentals = fetch_sec_fundamentals(ticker)
        # Price history is separate from Yahoo's restricted company-info API.
        try:
            history = yf.Ticker(ticker).history(period="1y", auto_adjust=True)
            closes = history["Close"].dropna()
            if len(closes) >= 2 and float(closes.iloc[0]) > 0:
                fundamentals["fiftyTwoWeekChange"] = float(closes.iloc[-1] / closes.iloc[0] - 1)
                fundamentals["price_as_of"] = str(closes.index[-1].date())
        except Exception:
            pass
        return {**info, **fundamentals}
    return info


def _score(info, sector_pe_median=None):
    """Sector-relative PE screening with an explicit coverage requirement."""
    forward_pe = _finite(info.get("forwardPE"))
    forward_pe = forward_pe if forward_pe is not None and forward_pe > 0 else None
    trailing_pe = _finite(info.get("trailingPE"))
    trailing_pe = trailing_pe if trailing_pe is not None and trailing_pe > 0 else None
    pe = forward_pe if forward_pe is not None else trailing_pe
    comparable_forward_pe = forward_pe if forward_pe is not None and forward_pe <= 200 else None
    pb = _finite(info.get("priceToBook"))
    roe = _finite(info.get("returnOnEquity"))
    growth = _finite(info.get("revenueGrowth"))
    margin = _finite(info.get("profitMargins"))
    momentum = _finite(info.get("fiftyTwoWeekChange"))
    metrics = {"pe": pe, "pb": pb, "roe": roe, "revenue_growth": growth,
               "profit_margin": margin, "year_change": momentum}
    checks = {
        "reasonable_pe": None if comparable_forward_pe is None or sector_pe_median is None else comparable_forward_pe <= sector_pe_median,
        "reasonable_pb": None if pb is None else 0 < pb <= 3,
        "positive_roe": None if roe is None else roe >= .10,
        "revenue_growth": None if growth is None else growth >= .05,
        "profitable": None if margin is None else margin > 0,
        "price_momentum": None if momentum is None else momentum >= 0,
    }
    available = [value for value in checks.values() if value is not None]
    return {
        "metrics": {**metrics, "pe_basis": "forward" if forward_pe is not None else "trailing" if pe is not None else None, "sector_pe_median": sector_pe_median,
                    "pe_discount_pct": round((1 - forward_pe / sector_pe_median) * 100, 2)
                    if comparable_forward_pe is not None and sector_pe_median else None},
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
    policy = SECTOR_POLICIES.get(sector, DEFAULT_POLICY)
    results, failures, records = [], {}, []
    # Bound concurrent requests to avoid sequential latency and provider overload.
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_fetch_info, ticker): ticker for ticker in UNIVERSE[market][sector]}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                info = future.result()
                if not isinstance(info, dict) or not info:
                    raise ValueError("기업 정보 없음")
                records.append((ticker, info))
            except Exception:
                failures[ticker] = "기업 정보 조회 실패"
    # A provider may return only names/tickers while fundamentals are unavailable.
    # Do not present such records as a valid valuation result or cache the outage.
    usable = sum(
        any(_finite(info.get(field)) is not None for field in FIELDS)
        for _, info in records
    )
    if usable == 0:
        raise RuntimeError("Fundamental data unavailable for all sampled companies")
    # SEC-only annual profit margin is insufficient for a multi-factor screen.
    # Keep this endpoint unavailable rather than render non-actionable cards.
    sufficient = sum(
        sum(_finite(info.get(field)) is not None for field in FIELDS) >= 4
        for _, info in records
    )
    if sufficient == 0:
        raise RuntimeError("Insufficient multi-factor data for sector screening")
    records.sort(key=lambda item: item[0])
    # Curated sample: never claim an industry-wide benchmark. Require 5
    # comparable positive forward PEs before allowing valuation labels.
    valid_pe = []
    for _, info in records:
        pe = _finite(info.get("forwardPE"))
        if pe is not None and 0 < pe <= 200:
            valid_pe.append(pe)
    sector_pe_median = statistics.median(valid_pe) if len(valid_pe) >= 5 else None
    sector_pe_mean = statistics.mean(valid_pe) if len(valid_pe) >= 5 else None
    # Cyclical semiconductor multiples are informational only until normalized
    # multi-year earnings are sourced and verified (never infer them from PE).
    semiconductor_cycle = {"status": "not_verified", "normalized_earnings": None} if sector == "semiconductors" else None
    bank_ratios = []
    if policy["primary"] == "pbr_roe":
        for _, company in records:
            pb = _finite(company.get("priceToBook"))
            roe = _finite(company.get("returnOnEquity"))
            if pb is not None and roe is not None and pb > 0 and roe > 0:
                bank_ratios.append(pb / roe)
    bank_median = statistics.median(bank_ratios) if len(bank_ratios) >= 5 else None
    for ticker, info in records:
        assessment = _score(info, sector_pe_median)
        # Valuation and investability are distinct: a low multiple is not
        # evidence of undervaluation without earnings quality and growth.
        discount = assessment["metrics"]["pe_discount_pct"]
        growth = assessment["metrics"]["revenue_growth"]
        roe = assessment["metrics"]["roe"]
        margin = assessment["metrics"]["profit_margin"]
        healthy = all(value is not None for value in (growth, roe, margin)) and growth >= 0 and roe > 0 and margin > 0
        pb = _finite(info.get("priceToBook"))
        roe_value = _finite(info.get("returnOnEquity"))
        bank_discount = (100 * (1 - (pb / roe_value) / bank_median)
                         if bank_median is not None and pb is not None and pb > 0
                         and roe_value is not None and roe_value > 0 else None)
        if policy["primary"] == "pbr_roe":
            valuation = "은행 상대가치 참고" if bank_discount is not None else "평가 보류"
        elif not policy["automatic_valuation"] or discount is None or not healthy:
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
            "bank_pbr_roe_discount_pct": round(bank_discount, 2) if bank_discount is not None else None,
            "valuation_basis": ("표본 Forward PER 및 최소 성장·수익성 검증" if policy["automatic_valuation"] else "업종 전용 재무지표 미검증"),
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
        "market": market, "sector": sector, "valuation_policy": policy, "as_of": datetime.now(timezone.utc).isoformat(),
        "sample_size": len(UNIVERSE[market][sector]),
        "results": results, "failures": failures,
        "semiconductor_cycle": semiconductor_cycle,
        "bank_pbr_roe_benchmark": {"median": round(bank_median, 4) if bank_median is not None else None,
                                   "valid_count": len(bank_ratios), "minimum_count": 5},
        "pe_benchmark": {"type": "curated_sample", "median": sector_pe_median,
                         "mean": round(sector_pe_mean, 2) if sector_pe_mean is not None else None,
                         "valid_count": len(valid_pe), "minimum_count": 5},
        "method": "임시 탐색 점수(6개 지표). PER 상대평가는 Forward PER 유효 표본 5개 이상인 경우만 사용. 가치평가와 투자매력도는 별개입니다.",
        "disclaimer": "제한된 표본의 정량 선별 결과이며 저평가 확정 또는 매수 추천이 아닙니다. PER 기준은 소규모 표본 중앙값이며 섹터 전체 평균이 아닙니다. 표본이 부족하면 가치평가를 보류합니다. 업종별 적정 PER/PBR이 달라 직접 비교에 주의하세요.",
    }
    CACHE[key] = (time.monotonic(), result)
    return result
