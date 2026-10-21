"""SEC companyfacts-shaped integration fixtures; synthetic, not live financial data."""
from scripts.pilot_sec_companyfacts import analyze_companyfacts


def test_sec_companyfacts_full_pipeline_with_realistic_shapes():
    accession = "0000320193-25-000001"
    payload = {
        "cik": 320193,
        "entityName": "Synthetic Example",
        "facts": {
            "us-gaap": {
                "StockholdersEquity": {"units": {"USD": [
                    {"filed": "2025-05-01", "end": "2025-03-31",
                     "val": 100_000_000, "form": "10-Q", "accn": accession},
                ]}},
                "CommonStockSharesOutstanding": {"units": {"shares": [
                    {"filed": "2025-05-01", "end": "2025-03-31",
                     "val": 10_000_000, "form": "10-Q", "accn": accession},
                ]}},
            },
            "dei": {},
        },
    }
    result = analyze_companyfacts(payload, cik="320193", as_of="2025-06-01")
    assert result["equity_filings"] == 1
    assert result["share_filings"] == 1
    assert result["strictly_matched_filings"] == 1
    assert result["coverage"]["filing_count"] == 1
    assert result["coverage"]["distinct_quarters"] == 1
    assert result["quarter_gaps"]["gap_count"] == 0
    assert result["coverage"]["investment_ready"] is False


def test_sec_companyfacts_dei_cover_page_shares_not_forced_to_match():
    accession = "0000320193-25-000002"
    payload = {
        "cik": 320193,
        "entityName": "Synthetic Example",
        "facts": {
            "us-gaap": {"StockholdersEquity": {"units": {"USD": [
                {"filed": "2025-05-01", "end": "2025-03-31",
                 "val": 100_000_000, "form": "10-Q", "accn": accession},
            ]}}},
            "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
                {"filed": "2025-05-01", "end": "2025-04-20",
                 "val": 10_000_000, "form": "10-Q", "accn": accession},
            ]}}},
        },
    }
    result = analyze_companyfacts(payload, cik="320193", as_of="2025-06-01")
    assert result["strictly_matched_filings"] == 0
    assert result["coverage"]["investment_ready"] is False
