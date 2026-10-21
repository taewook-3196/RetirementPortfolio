from services.sec_companyfacts_service import parse_sec_equity_filings


def test_only_published_sec_equity_facts_are_kept():
    payload = {"facts": {"us-gaap": {"StockholdersEquity": {"units": {"USD": [
        {"filed": "2025-02-10", "end": "2024-12-31", "val": 100, "form": "10-K", "accn": "a"},
        {"filed": "2025-04-01", "end": "2024-12-31", "val": 200, "form": "10-K", "accn": "b"},
        {"filed": "2025-01-01", "end": "2024-12-31", "val": 999, "form": "8-K", "accn": "c"},
    ]}}}}}
    result = parse_sec_equity_filings(payload, as_of="2025-03-01")
    assert result["status"] == "reference_only"
    assert len(result["filings"]) == 1
    assert result["filings"][0]["equity_usd"] == 100


def test_missing_and_future_records_withheld():
    assert parse_sec_equity_filings({}, as_of="2025-01-01")["status"] == "withheld"
    assert parse_sec_equity_filings({"facts": {"us-gaap": {}}}, as_of="2025-01-01")["status"] == "withheld"
