from services.sec_share_count_service import parse_sec_share_filings, match_equity_and_shares


def test_share_filings_exclude_future_disclosures():
    payload = {"facts": {"dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
        {"filed": "2025-02-01", "end": "2024-12-31", "val": 50, "form": "10-K", "accn": "a"},
        {"filed": "2025-04-01", "end": "2024-12-31", "val": 20, "form": "10-K", "accn": "b"},
    ]}}}}}
    result = parse_sec_share_filings(payload, as_of="2025-03-01")
    assert result["status"] == "reference_only"
    assert len(result["filings"]) == 1
    assert result["filings"][0]["shares"] == 50


def test_bps_pairing_requires_same_accession_and_period():
    equity = [{"filed": "2025-02-01", "period_end": "2024-12-31", "accession": "a", "equity_usd": 1000}]
    shares = [{"filed": "2025-02-02", "period_end": "2024-12-31", "accession": "a", "shares": 100}]
    matches = match_equity_and_shares(equity, shares)
    assert matches[0]["bps_unadjusted_usd"] == 10
    assert matches[0]["status"] == "requires_corporate_action_validation"
    assert match_equity_and_shares(equity, [{**shares[0], "accession": "b"}]) == []


def test_ambiguous_share_counts_block_pairing():
    equity = [{"filed": "2025-02-01", "period_end": "2024-12-31", "accession": "a", "equity_usd": 1000}]
    share = {"filed": "2025-02-01", "period_end": "2024-12-31", "accession": "a", "shares": 100}
    assert match_equity_and_shares(equity, [share, {**share, "shares": 200}]) == []
