"""Audit why SEC equity/share observations cannot safely yield historical BPS."""
from collections import Counter


def audit_sec_bps_matches(equity_filings, share_filings):
    """Report provenance coverage and mismatches without filling missing shares."""
    equities = list(equity_filings)
    shares = list(share_filings)
    share_by_accession = {}
    for item in shares:
        accession = item.get("accession")
        if accession:
            share_by_accession.setdefault(accession, []).append(item)
    reasons = Counter()
    matched = []
    for equity in equities:
        accession = equity.get("accession")
        period = equity.get("period_end")
        candidates = share_by_accession.get(accession, [])
        same_period = [s for s in candidates if s.get("period_end") == period]
        if not candidates:
            reasons["no_shares_for_accession"] += 1
        elif not same_period:
            reasons["share_period_mismatch"] += 1
        elif len(same_period) != 1:
            reasons["ambiguous_share_facts"] += 1
        elif equity.get("equity_usd", 0) <= 0 or same_period[0].get("shares", 0) <= 0:
            reasons["invalid_amount"] += 1
        else:
            matched.append({"accession": accession, "period_end": period})
    return {
        "status": "diagnostic_only",
        "equity_filing_count": len(equities),
        "share_filing_count": len(shares),
        "strict_match_count": len(matched),
        "unmatched_equity_count": len(equities) - len(matched),
        "reasons": dict(sorted(reasons.items())),
        "corporate_actions_verified": False,
        "investment_ready": False,
    }
