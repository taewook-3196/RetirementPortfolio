from services.sec_pbr_readiness_gate import summarize_sec_pbr_blockers


def test_blockers_identify_gaps_conflicts_and_missing_history():
    report = {
        "coverage": {"status": "withheld", "unvalidated_count": 2},
        "quarter_gaps": {"gap_count": 1},
        "period_conflicts": {"conflicting_period_count": 1},
        "strictly_matched_filings": 0,
        "source_verified": False,
        "match_audit": {"investment_ready": False},
    }
    result = summarize_sec_pbr_blockers(report)
    assert "missing_reporting_quarters" in result["blockers"]
    assert "conflicting_financial_period_values" in result["blockers"]
    assert "insufficient_historical_coverage" in result["blockers"]
    assert result["investment_ready"] is False


def test_even_sufficient_pilot_coverage_is_not_investment_ready():
    report = {
        "coverage": {"status": "pilot_coverage_sufficient", "unvalidated_count": 0},
        "quarter_gaps": {"gap_count": 0},
        "period_conflicts": {"conflicting_period_count": 0},
        "strictly_matched_filings": 30,
        "source_verified": True,
    }
    result = summarize_sec_pbr_blockers(report)
    assert result["investment_ready"] is False
    assert "live_price_and_point_in_time_validation_pending" in result["blockers"]
