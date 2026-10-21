from services.sec_pilot_batch_summary import summarize_sec_pilot_reports


def test_summary_reports_match_rate_and_not_ready():
    reports = [
        {"cik": "0000320193", "company": "A", "equity_filings": 4,
         "strictly_matched_filings": 1,
         "coverage": {"status": "withheld", "distinct_quarters": 1, "span_years": 0},
         "match_audit": {"reasons": {"share_period_mismatch": 3}}},
        {"cik": "0000789019", "company": "B", "equity_filings": 0,
         "strictly_matched_filings": 0,
         "coverage": {"status": "withheld"}, "match_audit": {}},
    ]
    result = summarize_sec_pilot_reports(reports)
    assert result["company_count"] == 2
    assert result["companies"][0]["match_rate_pct"] == 25.0
    assert result["companies"][1]["match_rate_pct"] is None
    assert result["investment_ready_count"] == 0
    assert all(not company["investment_ready"] for company in result["companies"])
