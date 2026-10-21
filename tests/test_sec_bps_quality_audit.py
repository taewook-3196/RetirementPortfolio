from services.sec_bps_quality_audit import audit_sec_bps_matches


def test_audit_explains_share_period_mismatch():
    equity = [{"accession": "a", "period_end": "2024-12-31", "equity_usd": 1000}]
    shares = [{"accession": "a", "period_end": "2025-01-31", "shares": 100}]
    result = audit_sec_bps_matches(equity, shares)
    assert result["reasons"]["share_period_mismatch"] == 1
    assert result["strict_match_count"] == 0
    assert result["investment_ready"] is False


def test_audit_counts_unambiguous_matches_only():
    equity = [
        {"accession": "a", "period_end": "2024-12-31", "equity_usd": 1000},
        {"accession": "b", "period_end": "2024-12-31", "equity_usd": 2000},
    ]
    shares = [
        {"accession": "a", "period_end": "2024-12-31", "shares": 100},
        {"accession": "b", "period_end": "2024-12-31", "shares": 100},
        {"accession": "b", "period_end": "2024-12-31", "shares": 200},
    ]
    result = audit_sec_bps_matches(equity, shares)
    assert result["strict_match_count"] == 1
    assert result["reasons"]["ambiguous_share_facts"] == 1
    assert result["unmatched_equity_count"] == 1
