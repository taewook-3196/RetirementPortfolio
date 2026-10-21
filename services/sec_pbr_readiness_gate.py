"""Consolidate SEC pilot diagnostics into explicit investment-use blockers."""


def summarize_sec_pbr_blockers(report):
    coverage = report.get("coverage") or {}
    gaps = report.get("quarter_gaps") or {}
    conflicts = report.get("period_conflicts") or {}
    audit = report.get("match_audit") or {}
    blockers = []
    if coverage.get("status") != "pilot_coverage_sufficient":
        blockers.append("insufficient_historical_coverage")
    if gaps.get("gap_count", 0) > 0:
        blockers.append("missing_reporting_quarters")
    if conflicts.get("conflicting_period_count", 0) > 0:
        blockers.append("conflicting_financial_period_values")
    if coverage.get("unvalidated_count", 0) > 0:
        blockers.append("corporate_actions_unverified")
    if not report.get("source_verified", False):
        blockers.append("source_provenance_unverified")
    if report.get("strictly_matched_filings", 0) == 0:
        blockers.append("no_strict_equity_share_matches")
    if audit.get("investment_ready") is False:
        blockers.append("bps_match_audit_not_investment_ready")
    # These pilots are not authorized for trading even if diagnostics pass.
    blockers.append("live_price_and_point_in_time_validation_pending")
    return {
        "status": "withheld",
        "investment_ready": False,
        "blockers": blockers,
        "blocker_count": len(blockers),
    }
