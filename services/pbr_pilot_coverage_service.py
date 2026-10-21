"""Summarize historical PBR input coverage without claiming investment readiness."""
from datetime import date


def assess_pbr_pilot_coverage(pairs, *, as_of, min_quarters=20, min_years=5):
    """Pairs must be disclosure-dated BPS matches with validation statuses."""
    try:
        cutoff = date.fromisoformat(as_of)
    except (TypeError, ValueError):
        return {"status": "withheld", "reason": "유효하지 않은 기준일입니다."}
    if cutoff > date.today():
        return {"status": "withheld", "reason": "미래 기준일은 허용하지 않습니다."}
    dated = []
    for pair in pairs:
        try:
            filed = date.fromisoformat(pair["filed"])
            period = date.fromisoformat(pair["period_end"])
            bps = float(pair["bps_unadjusted_usd"])
        except (TypeError, ValueError, KeyError, OverflowError):
            continue
        if period <= filed <= cutoff and bps > 0 and bps < float("inf"):
            dated.append((period, pair.get("status")))
    quarters = sorted({(day.year, (day.month - 1) // 3 + 1) for day, _ in dated})
    years = (max((day for day, _ in dated), default=cutoff) -
             min((day for day, _ in dated), default=cutoff)).days / 365.25
    validated = sum(status == "corporate_actions_verified" for _, status in dated)
    coverage_ok = len(quarters) >= min_quarters and years >= min_years
    return {
        "status": "pilot_coverage_sufficient" if coverage_ok else "withheld",
        "investment_ready": False,
        "filing_count": len(dated),
        "quarter_basis": "financial_period_end",
        "distinct_quarters": len(quarters),
        "span_years": round(years, 2),
        "corporate_action_validated_count": validated,
        "unvalidated_count": len(dated) - validated,
        "reason": "주식분할·주식 종류·가격 정합성 및 실제 공급원 검증 전에는 투자 추천에 사용하지 않습니다.",
    }
