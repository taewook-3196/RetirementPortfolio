"""Read-only, explainable equity screening. Educational research, not trade advice.

Uses Yahoo Finance fundamentals when available; missing metrics never score as zero.
Universe is a curated sample, not all listed stocks.
"""
from datetime import datetime, timezone
import math
import statistics

from services.sector_taxonomy import us_sector_metadata
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
          "revenueGrowth", "earningsGrowth", "profitMargins", "fiftyTwoWeekChange",
          "debtToEquity", "currentRatio")


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
    earnings_growth = _finite(info.get("earningsGrowth"))
    debt_to_equity = _finite(info.get("debtToEquity"))
    current_ratio = _finite(info.get("currentRatio"))
    momentum = _finite(info.get("fiftyTwoWeekChange"))
    metrics = {"pe": pe, "pb": pb, "roe": roe, "revenue_growth": growth,
               "profit_margin": margin, "earnings_growth": earnings_growth, "year_change": momentum,
               "debt_to_equity": debt_to_equity, "current_ratio": current_ratio}
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
        "coverage_pct": round(100 * len(available) / len(checks), 1),
        "evidence_level": "충분" if len(available) == len(checks) else "부분" if len(available) >= 4 else "부족",
        "score": round(100 * sum(available) / len(available), 1) if available else None,
        "evidence_adjusted_score": round(100 * sum(available) / len(checks), 1),
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
        earnings_growth = assessment["metrics"]["earnings_growth"]
        debt_to_equity = assessment["metrics"]["debt_to_equity"]
        current_ratio = assessment["metrics"]["current_ratio"]
        # Balance-sheet red flags are a veto, not a universal cross-sector score.
        # Yahoo debtToEquity is reported as a percentage (e.g. 250 means 2.5x).
        # Bank leverage and real-estate liquidity require industry-specific
        # measures; generic corporate thresholds must not label them risky.
        generic_balance_sheet_policy = sector not in {"financials", "banks", "real_estate"}
        balance_sheet_red_flag = generic_balance_sheet_policy and (
            (debt_to_equity is not None and debt_to_equity > 300)
            or (current_ratio is not None and current_ratio < 0.8))
        healthy = (all(value is not None for value in (growth, roe, margin))
                   and growth >= 0 and roe > 0 and margin > 0
                   and (earnings_growth is None or earnings_growth >= 0)
                   and not balance_sheet_red_flag)
        pb = _finite(info.get("priceToBook"))
        roe_value = _finite(info.get("returnOnEquity"))
        bank_discount = (100 * (1 - (pb / roe_value) / bank_median)
                         if bank_median is not None and pb is not None and pb > 0
                         and roe_value is not None and roe_value > 0 else None)
        if policy["primary"] == "pbr_roe":
            valuation = "PBR/ROE 상대가치 참고" if bank_discount is not None else "평가 보류"
        elif not policy["automatic_valuation"] or discount is None or not healthy or assessment["coverage"] < 5:
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
        reasons = []
        cautions = []
        if discount is not None:
            reasons.append(f"표본 Forward PER 중앙값 대비 {discount:.1f}% 할인" if discount >= 0
                           else f"표본 Forward PER 중앙값 대비 {-discount:.1f}% 할증")
        if growth is not None and growth > 0:
            reasons.append("매출 성장률 양수")
        if roe is not None and roe > 0 and margin is not None and margin > 0:
            reasons.append("ROE와 순이익률 양수")
        if earnings_growth is not None and earnings_growth < 0:
            cautions.append("이익 성장률 감소")
        if balance_sheet_red_flag:
            cautions.append("일반 기업 기준 재무건전성 위험")
        if discount is None:
            cautions.append("Forward PER 비교 표본 부족 또는 비교 불가")
        if assessment["coverage"] < 5:
            cautions.append("평가 근거 부족")
        if not policy["automatic_valuation"]:
            cautions.append("업종 전용 평가 기준 미검증: 자동 저평가 판정 제외")
        if valuation == "평가 보류" and not cautions:
            cautions.append("성장성·수익성 요건 미충족 또는 자료 부족")
        results.append({
            "reasons": reasons,
            "cautions": cautions,
            "valuation_label": valuation,
            "balance_sheet_red_flag": balance_sheet_red_flag,
            "bank_pbr_roe_discount_pct": round(bank_discount, 2) if bank_discount is not None else None,
            "valuation_basis": ("표본 Forward PER 및 최소 성장·수익성 검증" if policy["automatic_valuation"] else "표본 PBR/ROE 상대비교(투자판단 불가)" if policy["primary"] == "pbr_roe" and bank_discount is not None else "업종 전용 재무지표 미검증"),
            "ticker": ticker,
            "name": str(info.get("shortName") or ticker)[:120],
            "currency": str(info.get("currency") or ""),
            **assessment,
        })
    # Explicit curated reference, not an inferred market-cap leader.
    # Missing fundamentals remain null rather than being interpreted as zero.
    reference_ticker = UNIVERSE[market][sector][0]
    reference = next((row for row in results if row["ticker"] == reference_ticker), None)
    comparison_keys = ("pe", "pb", "roe", "revenue_growth", "earnings_growth",
                       "profit_margin", "year_change", "debt_to_equity", "current_ratio")
    for row in results:
        row["reference_ticker"] = reference_ticker
        row["reference_comparison"] = {
            key: (round(row["metrics"][key] - reference["metrics"][key], 4)
                  if reference is not None and row["metrics"].get(key) is not None
                  and reference["metrics"].get(key) is not None
                  and (key != "pe" or row["metrics"]["pe_basis"] == reference["metrics"]["pe_basis"])
                  else None)
            for key in comparison_keys
        }
    results.sort(key=lambda item: (
        not item["eligible"],
        -((item["score"] or 0) * item["coverage"] / item["total_metrics"]),
        -item["coverage"],
        -(item["score"] if item["score"] is not None else -1),
        item["ticker"],
    ))
    result = {
        **(us_sector_metadata(sector) if market == "us" else {}),
        "market": market, "sector": sector, "valuation_policy": policy, "as_of": datetime.now(timezone.utc).isoformat(),
        "reference": {"ticker": reference_ticker, "name": reference["name"] if reference else reference_ticker,
                      "metrics": reference["metrics"] if reference else None,
                      "selection_method": "curated_first_ticker",
                      "selection_verified": False,
                      "data_available": reference is not None,
                      "basis": "표본 목록 첫 번째 사전 지정 종목(시가총액·유동성 기준 대표주 검증 전)"},
        "sample_size": len(UNIVERSE[market][sector]),
        "results": results, "failures": failures,
        "semiconductor_cycle": semiconductor_cycle,
        "bank_pbr_roe_benchmark": {"median": round(bank_median, 4) if bank_median is not None else None,
                                   "valid_count": len(bank_ratios), "minimum_count": 5},
        "pe_benchmark": {"type": "curated_sample", "median": sector_pe_median,
                         "mean": round(sector_pe_mean, 2) if sector_pe_mean is not None else None,
                         "valid_count": len(valid_pe), "minimum_count": 5},
        "method": "임시 탐색 점수(확보된 지표 중 충족 비율), 근거 확보율(전체 6개 지표 중 확보 비율), 근거 반영 점수(전체 6개 중 충족 비율)는 별개입니다. 순위는 근거 반영 점수를 우선 사용합니다. PER 상대평가는 Forward PER 유효 표본 5개 이상인 경우만 사용. 가치평가와 투자매력도는 별개입니다.",
        "disclaimer": "제한된 표본의 정량 선별 결과이며 저평가 확정 또는 매수 추천이 아닙니다. PER 기준은 소규모 표본 중앙값이며 섹터 전체 평균이 아닙니다. 표본이 부족하면 가치평가를 보류합니다. 업종별 적정 PER/PBR이 달라 직접 비교에 주의하세요.",
    }
    CACHE[key] = (time.monotonic(), result)
    return result
