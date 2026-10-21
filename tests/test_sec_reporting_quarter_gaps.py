from services.sec_reporting_quarter_gaps import audit_reporting_quarter_gaps


def test_gap_between_financial_reporting_quarters():
    rows = [
        {"filed": "2024-05-01", "period_end": "2024-03-31"},
        {"filed": "2024-11-01", "period_end": "2024-09-30"},
    ]
    result = audit_reporting_quarter_gaps(rows, as_of="2025-01-01")
    assert result["observed_quarters"] == 2
    assert result["missing_quarters"] == ["2024-Q2"]
    assert result["gap_count"] == 1
    assert result["investment_ready"] is False


def test_future_filing_not_counted():
    rows = [{"filed": "2027-01-01", "period_end": "2024-03-31"}]
    assert audit_reporting_quarter_gaps(rows, as_of="2025-01-01")["observed_quarters"] == 0
