"""Offline tests for SEC annual facts mapping and Yahoo fallback."""
from unittest.mock import patch
import pytest
from services.sec_edgar_fundamentals import _annual_facts, fetch_sec_fundamentals
from services.sector_value_screening_service import _fetch_info


def test_annual_facts_prefers_latest_fiscal_year():
    facts = {"facts": {"us-gaap": {"NetIncomeLoss": {"units": {"USD": [
        {"form": "10-K", "fy": 2024, "fp": "FY", "start": "2024-01-01", "end": "2024-12-31", "filed": "2025-02-01", "val": 50},
        {"form": "10-K", "fy": 2025, "fp": "FY", "start": "2025-01-01", "end": "2025-12-31", "filed": "2026-02-01", "val": 80},
    ]}}}}}
    assert _annual_facts(facts, ("NetIncomeLoss",)) == (80.0, "2025-12-31")


def test_sec_rejects_mismatched_annual_periods():
    facts = {"entityName": "Example", "facts": {"us-gaap": {
        "Revenues": {"units": {"USD": [{"form": "10-K", "fy": 2025, "fp": "FY", "start": "2025-01-01", "end": "2025-12-31", "val": 100}]}},
        "NetIncomeLoss": {"units": {"USD": [{"form": "10-K", "fy": 2024, "fp": "FY", "start": "2024-01-01", "end": "2024-12-31", "val": 20}]}},
    }}}
    with patch("services.sec_edgar_fundamentals._cik_for_ticker", return_value=123), patch("services.sec_edgar_fundamentals._cached", return_value=facts):
        with pytest.raises(ValueError, match="Comparable"):
            fetch_sec_fundamentals("TEST")


def test_yahoo_unavailable_uses_sec_verified_profit_margin():
    with patch("yfinance.Ticker", side_effect=RuntimeError("401")), patch("services.sec_edgar_fundamentals.fetch_sec_fundamentals", return_value={"shortName": "Example", "profitMargins": .2}):
        assert _fetch_info("AAPL")["profitMargins"] == .2


def test_latest_revenue_across_multiple_taxonomy_tags():
    facts = {"facts": {"us-gaap": {
        "Revenues": {"units": {"USD": [{"form": "10-K", "fy": 2024, "fp": "FY", "start": "2024-01-01", "end": "2024-12-31", "val": 90}]}},
        "SalesRevenueNet": {"units": {"USD": [{"form": "10-K", "fy": 2025, "fp": "FY", "start": "2025-01-01", "end": "2025-12-31", "val": 120}]}},
    }}}
    assert _annual_facts(facts, ("Revenues", "SalesRevenueNet")) == (120.0, "2025-12-31")


def test_sec_roe_only_with_matching_equity_fiscal_date():
    from services.sec_edgar_fundamentals import fetch_sec_fundamentals
    def flow(val):
        return {"units": {"USD": [{"form": "10-K", "fy": 2025, "fp": "FY", "start": "2025-01-01", "end": "2025-12-31", "val": val}]}}
    def balance(end):
        return {"units": {"USD": [{"form": "10-K", "end": end, "val": 200}]}}
    facts = {"facts": {"us-gaap": {"Revenues": flow(100), "NetIncomeLoss": flow(20), "StockholdersEquity": balance("2025-12-31")}}}
    with patch("services.sec_edgar_fundamentals._cik_for_ticker", return_value=123), patch("services.sec_edgar_fundamentals._cached", return_value=facts):
        assert fetch_sec_fundamentals("TEST")["returnOnEquity"] == .1
        facts["facts"]["us-gaap"]["StockholdersEquity"] = balance("2024-12-31")
        assert fetch_sec_fundamentals("TEST")["returnOnEquity"] is None


def test_sec_shares_are_dated_and_do_not_infer_current_valuation():
    from services.sec_edgar_fundamentals import _shares_outstanding
    facts = {"facts": {"dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
        {"form": "10-K", "end": "2024-12-31", "val": 100},
        {"form": "10-K", "end": "2025-12-31", "val": 80},
    ]}}}}}
    assert _shares_outstanding(facts) == (80.0, "2025-12-31")
    assert _shares_outstanding({"facts": {}}) == (None, None)


def test_fiscal_end_share_count_requires_matching_date():
    from services.sec_edgar_fundamentals import fetch_sec_fundamentals
    def flow(val):
        return {"units": {"USD": [{"form": "10-K", "fy": 2025, "fp": "FY", "start": "2025-01-01", "end": "2025-12-31", "val": val}]}}
    facts = {"facts": {
        "us-gaap": {"Revenues": flow(100), "NetIncomeLoss": flow(20)},
        "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
            {"form": "10-K", "end": "2026-02-01", "val": 10}
        ]}}},
    }}
    with patch("services.sec_edgar_fundamentals._cik_for_ticker", return_value=123), patch("services.sec_edgar_fundamentals._cached", return_value=facts):
        result = fetch_sec_fundamentals("TEST")
        assert result["shares_outstanding"] == 10
        assert result["shares_match_fiscal_end"] is False
        assert result["fiscal_end_shares"] is None
