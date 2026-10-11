"""Regression tests for the explainable sector stock screener."""
from unittest.mock import patch
import pytest
from services.sector_value_screening_service import (
    _score, screen_sector, CACHE,
)


def test_missing_data_is_not_treated_as_failure():
    result = _score({"forwardPE": 12})
    assert result["coverage"] == 0
    assert result["score"] is None
    assert result["eligible"] is False
    assert result["checks"]["positive_roe"] is None


def test_negative_pe_does_not_qualify():
    result = _score({"forwardPE": -4, "trailingPE": -5})
    assert result["checks"]["reasonable_pe"] is None


def test_screen_handles_partial_provider_failures():
    CACHE.clear()
    def fake_info(ticker):
        if ticker == "AAPL":
            raise RuntimeError("provider unavailable")
        return {"shortName": ticker, "forwardPE": 15, "priceToBook": 2,
                "returnOnEquity": .2, "revenueGrowth": .1,
                "profitMargins": .2, "fiftyTwoWeekChange": .05}
    with patch("services.sector_value_screening_service._fetch_info", side_effect=fake_info):
        result = screen_sector("us", "technology")
    assert "AAPL" in result["failures"]
    assert result["results"][0]["eligible"]
    assert result["pe_benchmark"]["median"] == 15
    assert result["pe_benchmark"]["valid_count"] == 11
    assert result["pe_benchmark"]["minimum_count"] == 5
    assert all(row["valuation_label"] == "평가 보류" for row in result["results"])
    assert result["results"][0]["score"] == 100


def test_invalid_sector_is_rejected():
    with pytest.raises(ValueError):
        screen_sector("us", "not_a_sector")


def test_sector_relative_pe_and_insufficient_sample():
    assert _score({"forwardPE": 22}, sector_pe_median=30)["checks"]["reasonable_pe"] is True
    assert _score({"forwardPE": 18}, sector_pe_median=10)["checks"]["reasonable_pe"] is False
    assert _score({"forwardPE": 18})["checks"]["reasonable_pe"] is None
    assert _score({"forwardPE": 22}, sector_pe_median=30)["metrics"]["pe_discount_pct"] == 26.67


def test_forward_pe_only_and_profitability_gate():
    CACHE.clear()
    def fake_info(ticker):
        return {"shortName": ticker, "trailingPE": 12, "returnOnEquity": .2,
                "revenueGrowth": .1, "profitMargins": .2}
    with patch("services.sector_value_screening_service._fetch_info", side_effect=fake_info):
        result = screen_sector("us", "financials")
    assert result["pe_benchmark"]["valid_count"] == 0
    assert all(row["valuation_label"] == "평가 보류" for row in result["results"])


def test_banks_require_specialized_valuation_inputs():
    CACHE.clear()
    def fake_info(ticker):
        return {"shortName": ticker, "forwardPE": 8, "priceToBook": 1,
                "returnOnEquity": .15, "revenueGrowth": .1, "profitMargins": .2}
    with patch("services.sector_value_screening_service._fetch_info", side_effect=fake_info):
        result = screen_sector("us", "financials")
    assert result["valuation_policy"]["primary"] == "pbr_roe"
    assert result["bank_pbr_roe_benchmark"]["valid_count"] >= 5
    assert all(row["valuation_label"] == "은행 상대가치 참고" for row in result["results"])
    assert all(row["bank_pbr_roe_discount_pct"] == 0 for row in result["results"])


def test_semiconductors_do_not_claim_normalized_earnings():
    CACHE.clear()
    def fake_info(ticker):
        return {"shortName": ticker, "forwardPE": 8, "priceToBook": 1,
                "returnOnEquity": .2, "revenueGrowth": .1, "profitMargins": .2}
    with patch("services.sector_value_screening_service._fetch_info", side_effect=fake_info):
        result = screen_sector("kr", "semiconductors")
    assert result["semiconductor_cycle"]["status"] == "not_verified"
    assert all(row["valuation_label"] == "평가 보류" for row in result["results"])
