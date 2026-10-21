"""Known SEC CIKs for a small reproducible US free-data feasibility pilot.

The mappings identify entities only; they do not imply financial-data coverage.
"""
SEC_PILOT_COMPANIES = {
    "AAPL": {"cik": "0000320193", "name": "Apple Inc."},
    "MSFT": {"cik": "0000789019", "name": "Microsoft Corporation"},
    "JNJ": {"cik": "0000200406", "name": "Johnson & Johnson"},
}


def pilot_companyfacts_urls():
    return {
        ticker: f"https://data.sec.gov/api/xbrl/companyfacts/CIK{info['cik']}.json"
        for ticker, info in SEC_PILOT_COMPANIES.items()
    }
