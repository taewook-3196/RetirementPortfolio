from unittest.mock import patch

from scripts.pilot_sec_companyfacts import run_pilot


def test_online_sec_pilot_reports_readiness_blockers():
    payload = {"cik": 320193, "entityName": "Synthetic SEC Company",
               "facts": {"us-gaap": {}, "dei": {}}}
    with patch("scripts.pilot_sec_companyfacts.fetch_sec_companyfacts", return_value=payload):
        result = run_pilot("0000320193", user_agent="Research real@domain.org", as_of="2025-06-01")
    assert result["source"] == "sec_companyfacts_direct_api"
    assert result["source_verified"] is True
    assert result["pbr_readiness"]["investment_ready"] is False
    assert "insufficient_historical_coverage" in result["pbr_readiness"]["blockers"]
    assert "live_price_and_point_in_time_validation_pending" in result["pbr_readiness"]["blockers"]


def test_online_sec_pilot_rejects_mismatched_response_company():
    payload = {"cik": 789019, "entityName": "Wrong company",
               "facts": {"us-gaap": {}, "dei": {}}}
    with patch("scripts.pilot_sec_companyfacts.fetch_sec_companyfacts", return_value=payload):
        try:
            run_pilot("0000320193", user_agent="Research real@domain.org", as_of="2025-06-01")
            assert False, "A mismatched CIK must fail"
        except ValueError as exc:
            assert "CIK" in str(exc)
