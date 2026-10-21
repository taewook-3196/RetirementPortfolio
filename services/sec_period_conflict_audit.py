"""Detect conflicting SEC equity/BPS observations for the same report period.

Conflicts are diagnostic only; they must not be silently selected as investment data.
"""
from collections import defaultdict


def audit_sec_period_conflicts(equity_filings, bps_matches):
    equity_by_period = defaultdict(set)
    for row in equity_filings:
        try:
            key = row["period_end"]
            value = float(row["equity_usd"])
            if value > 0:
                equity_by_period[key].add(value)
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    bps_by_period = defaultdict(set)
    for row in bps_matches:
        try:
            key = row["period_end"]
            value = float(row["bps_unadjusted_usd"])
            if value > 0:
                bps_by_period[key].add(value)
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    equity_conflicts = sorted(period for period, values in equity_by_period.items() if len(values) > 1)
    bps_conflicts = sorted(period for period, values in bps_by_period.items() if len(values) > 1)
    return {
        "status": "diagnostic_only",
        "equity_conflicting_periods": equity_conflicts,
        "bps_conflicting_periods": bps_conflicts,
        "conflicting_period_count": len(set(equity_conflicts) | set(bps_conflicts)),
        "investment_ready": False,
        "note": "공시 수정·재작성 및 관측값 차이를 검증하기 전 해당 기간의 PBR 사용 금지.",
    }
