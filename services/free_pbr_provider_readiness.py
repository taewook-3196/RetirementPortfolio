"""Read-only readiness checklist for free historical PBR sources.

This module does not claim that a provider has been tested or is available.
"""
FREE_PROVIDER_PLAN = {
    "us": {
        "fundamentals": "SEC EDGAR companyfacts and submissions",
        "authentication": "Identifying User-Agent with real operator contact required",
        "pilot_tickers": ("AAPL", "MSFT", "JNJ"),
        "blocking_checks": (
            "Disclosed filing date and original accession available",
            "Equity attributable to common shareholders and compatible shares outstanding",
            "Restatements and stock splits handled point-in-time",
            "Historical prices on same currency and per-share basis",
            "At least 20 distinct quarters over five years",
        ),
    },
    "kr": {
        "fundamentals": "OpenDART quarterly financial statement and disclosure search",
        "authentication": "Free OpenDART API key required",
        "pilot_tickers": ("005930", "000660", "005380"),
        "blocking_checks": (
            "Corp code mapped to stock ticker",
            "Disclosure receipt date and consolidated statements resolved",
            "Controlling shareholder equity and common share count consistent",
            "Corrections and corporate actions handled point-in-time",
            "At least 20 distinct quarters over five years",
        ),
    },
}


def free_provider_readiness(market, *, fundamentals_verified=False,
                            price_history_verified=False,
                            license_reviewed=False,
                            corporate_actions_verified=False):
    """Explicitly withhold production PBR until every external gate is passed."""
    if market not in FREE_PROVIDER_PLAN:
        return {"status": "withheld", "reason": "지원하지 않는 시장입니다."}
    gates = {
        "fundamentals_verified": bool(fundamentals_verified),
        "price_history_verified": bool(price_history_verified),
        "license_reviewed": bool(license_reviewed),
        "corporate_actions_verified": bool(corporate_actions_verified),
    }
    return {
        "status": "pilot_ready" if all(gates.values()) else "withheld",
        "market": market,
        "gates": gates,
        "missing": [key for key, passed in gates.items() if not passed],
        "plan": FREE_PROVIDER_PLAN[market],
        "note": "pilot_ready는 외부 검증 체크 완료만 뜻하며 실시간 API 가동이나 투자 추천을 보장하지 않습니다.",
    }
