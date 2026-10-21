from datetime import date, timedelta
from services.pbr_pilot_coverage_service import assess_pbr_pilot_coverage


def test_short_history_withheld():
    result = assess_pbr_pilot_coverage(
        [{"filed": "2025-01-01", "bps_unadjusted_usd": 10,
          "status": "requires_corporate_action_validation"}],
        as_of="2025-12-31",
    )
    assert result["status"] == "withheld"
    assert result["investment_ready"] is False
    assert result["unvalidated_count"] == 1


def test_long_history_never_implies_investment_readiness():
    rows = [
        {"filed": (date(2018, 1, 1) + timedelta(days=i * 100)).isoformat(),
         "bps_unadjusted_usd": 10, "status": "requires_corporate_action_validation"}
        for i in range(27)
    ]
    result = assess_pbr_pilot_coverage(rows, as_of="2026-01-01")
    assert result["status"] == "pilot_coverage_sufficient"
    assert result["investment_ready"] is False
    assert result["unvalidated_count"] == 27


def test_future_observations_ignored():
    result = assess_pbr_pilot_coverage(
        [{"filed": "2027-01-01", "bps_unadjusted_usd": 10}],
        as_of="2026-01-01",
    )
    assert result["filing_count"] == 0
