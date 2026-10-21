"""Diagnose gaps in financial-reporting-quarter coverage for SEC BPS pilots."""
from datetime import date


def audit_reporting_quarter_gaps(pairs, *, as_of):
    try:
        cutoff = date.fromisoformat(as_of)
    except (TypeError, ValueError):
        return {"status": "withheld", "reason": "invalid_as_of"}
    if cutoff > date.today():
        return {"status": "withheld", "reason": "future_as_of"}
    quarters = set()
    for pair in pairs:
        try:
            filed = date.fromisoformat(pair["filed"])
            period = date.fromisoformat(pair["period_end"])
        except (KeyError, TypeError, ValueError):
            continue
        if period <= filed <= cutoff:
            quarters.add(period.year * 4 + (period.month - 1) // 3)
    if not quarters:
        return {"status": "withheld", "observed_quarters": 0, "missing_quarters": [], "gap_count": 0}
    lower, upper = min(quarters), max(quarters)
    missing = sorted(set(range(lower, upper + 1)) - quarters)
    def label(index):
        return f"{(index - 1) // 4}-Q{(index - 1) % 4 + 1}"
    return {
        "status": "diagnostic_only",
        "observed_quarters": len(quarters),
        "expected_quarters_between_first_last": upper - lower + 1,
        "gap_count": len(missing),
        "missing_quarters": [label(index) for index in missing],
        "investment_ready": False,
    }
