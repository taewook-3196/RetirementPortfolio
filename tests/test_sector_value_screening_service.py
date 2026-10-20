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
    assert result["reference"]["selection_method"] == "curated_first_ticker"
    assert result["reference"]["selection_verified"] is False
    assert result["reference"]["data_available"] is True
    assert result["results"][0]["eligible"]
    assert result["pe_benchmark"]["median"] == 15
    assert result["pe_benchmark"]["valid_count"] == 11
    assert result["pe_benchmark"]["minimum_count"] == 5
    assert all(row["valuation_label"] == "상대 적정" for row in result["results"])
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
    assert all(row["valuation_label"] == "PBR/ROE 상대가치 참고" for row in result["results"])
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


def test_score_and_evidence_coverage_are_distinct():
    complete = _score({"forwardPE": 10, "priceToBook": 2, "returnOnEquity": .2,
                       "revenueGrowth": .1, "profitMargins": .2,
                       "fiftyTwoWeekChange": .1}, sector_pe_median=20)
    partial = _score({"forwardPE": 10, "priceToBook": 2, "returnOnEquity": .2,
                      "revenueGrowth": .1}, sector_pe_median=20)
    sparse = _score({"forwardPE": 10}, sector_pe_median=20)
    assert complete["score"] == partial["score"] == 100
    assert complete["coverage_pct"] == 100
    assert complete["evidence_level"] == "충분"
    assert partial["coverage_pct"] == 66.7
    assert partial["evidence_level"] == "부분"
    assert sparse["coverage_pct"] == 16.7
    assert sparse["evidence_level"] == "부족"
    assert sparse["eligible"] is False


def test_evidence_adjusted_score_matches_six_check_ranking_basis():
    complete = _score({"forwardPE": 10, "priceToBook": 2, "returnOnEquity": .2,
                       "revenueGrowth": .1, "profitMargins": .2,
                       "fiftyTwoWeekChange": -.1}, sector_pe_median=20)
    partial = _score({"forwardPE": 10, "priceToBook": 2, "returnOnEquity": .2,
                      "revenueGrowth": .1}, sector_pe_median=20)
    assert complete["score"] == 83.3
    assert complete["evidence_adjusted_score"] == 83.3
    assert partial["score"] == 100
    assert partial["evidence_adjusted_score"] == 66.7
    assert _score({})["evidence_adjusted_score"] == 0


def test_automatic_valuation_requires_five_available_checks():
    CACHE.clear()
    def fake_info(ticker):
        info = {"forwardPE": 10, "returnOnEquity": .2,
                "revenueGrowth": .1, "profitMargins": .2}
        if ticker != "MSFT":
            info["priceToBook"] = 2
        return info
    with patch("services.sector_value_screening_service._fetch_info", side_effect=fake_info):
        result = screen_sector("us", "technology")
    msft = next(row for row in result["results"] if row["ticker"] == "MSFT")
    assert msft["coverage"] == 4
    assert msft["eligible"] is True
    assert msft["valuation_label"] == "평가 보류"
    other = next(row for row in result["results"] if row["ticker"] == "AAPL")
    assert other["coverage"] == 5
    assert other["valuation_label"] == "상대 적정"
    CACHE.clear()


def test_contracting_earnings_block_automatic_undervaluation_label():
    CACHE.clear()
    def fake_info(ticker):
        return {"shortName": ticker, "forwardPE": 20 if ticker == "MSFT" else 40,
                "priceToBook": 2, "returnOnEquity": .2, "revenueGrowth": .1,
                "profitMargins": .2, "fiftyTwoWeekChange": .05,
                "earningsGrowth": -.2 if ticker == "MSFT" else .1}
    with patch("services.sector_value_screening_service._fetch_info", side_effect=fake_info):
        result = screen_sector("us", "technology")
    msft = next(row for row in result["results"] if row["ticker"] == "MSFT")
    assert msft["metrics"]["earnings_growth"] == -.2
    assert msft["metrics"]["pe_discount_pct"] == 50
    assert msft["valuation_label"] == "평가 보류"
    CACHE.clear()


def test_balance_sheet_red_flags_block_automatic_value_labels():
    CACHE.clear()
    def fake_info(ticker):
        return {"shortName": ticker, "forwardPE": 10 if ticker == "MSFT" else 20,
                "priceToBook": 2, "returnOnEquity": .2, "revenueGrowth": .1,
                "earningsGrowth": .1, "profitMargins": .2, "fiftyTwoWeekChange": .05,
                "debtToEquity": 350 if ticker == "MSFT" else 50,
                "currentRatio": 1.5}
    with patch("services.sector_value_screening_service._fetch_info", side_effect=fake_info):
        result = screen_sector("us", "technology")
    msft = next(row for row in result["results"] if row["ticker"] == "MSFT")
    assert msft["balance_sheet_red_flag"] is True
    assert msft["valuation_label"] == "평가 보류"
    assert msft["metrics"]["debt_to_equity"] == 350
    CACHE.clear()


def test_low_liquidity_blocks_automatic_value_label():
    CACHE.clear()
    def fake_info(ticker):
        return {"shortName": ticker, "forwardPE": 10 if ticker == "MSFT" else 20,
                "priceToBook": 2, "returnOnEquity": .2, "revenueGrowth": .1,
                "profitMargins": .2, "fiftyTwoWeekChange": .05,
                "currentRatio": .6 if ticker == "MSFT" else 1.5}
    with patch("services.sector_value_screening_service._fetch_info", side_effect=fake_info):
        result = screen_sector("us", "technology")
    msft = next(row for row in result["results"] if row["ticker"] == "MSFT")
    assert msft["balance_sheet_red_flag"] is True
    assert msft["valuation_label"] == "평가 보류"
    CACHE.clear()


def test_financial_and_real_estate_sectors_do_not_use_generic_balance_sheet_veto():
    for sector in ("financials", "real_estate"):
        CACHE.clear()
        def fake_info(ticker):
            return {"shortName": ticker, "forwardPE": 12, "priceToBook": 1.5,
                    "returnOnEquity": .15, "revenueGrowth": .08,
                    "profitMargins": .2, "fiftyTwoWeekChange": .03,
                    "debtToEquity": 700, "currentRatio": .4}
        with patch("services.sector_value_screening_service._fetch_info", side_effect=fake_info):
            result = screen_sector("us", sector)
        assert result["results"]
        assert all(row["balance_sheet_red_flag"] is False for row in result["results"])
    CACHE.clear()


def test_sector_reference_comparison_preserves_missing_data():
    CACHE.clear()
    def fake_info(ticker):
        return {"shortName": ticker, "forwardPE": 20 if ticker == "MSFT" else 30,
                "returnOnEquity": .2 if ticker == "MSFT" else None,
                "revenueGrowth": .1, "profitMargins": .2}
    with patch("services.sector_value_screening_service._fetch_info", side_effect=fake_info):
        result = screen_sector("us", "technology")
    assert result["reference"]["ticker"] == "MSFT"
    assert result["reference"]["metrics"]["pe"] == 20
    msft = next(row for row in result["results"] if row["ticker"] == "MSFT")
    aapl = next(row for row in result["results"] if row["ticker"] == "AAPL")
    assert msft["reference_comparison"]["pe"] == 0
    assert aapl["reference_comparison"]["pe"] == 10
    assert aapl["reference_comparison"]["roe"] is None
    CACHE.clear()


def test_sector_valuation_exposes_reasons_and_cautions():
    CACHE.clear()
    def fake_info(ticker):
        return {"shortName": ticker, "forwardPE": 12 if ticker == "MSFT" else 20,
                "returnOnEquity": .18, "revenueGrowth": .08,
                "profitMargins": .2, "earningsGrowth": -.12 if ticker == "MSFT" else .1,
                "fiftyTwoWeekChange": .1}
    with patch("services.sector_value_screening_service._fetch_info", side_effect=fake_info):
        result = screen_sector("us", "technology")
    msft = next(row for row in result["results"] if row["ticker"] == "MSFT")
    assert msft["valuation_label"] == "평가 보류"
    assert "이익 성장률 감소" in msft["cautions"]
    assert any("할인" in reason for reason in msft["reasons"])
    CACHE.clear()


def test_sector_reference_pe_does_not_mix_forward_and_trailing():
    CACHE.clear()
    def fake_info(ticker):
        data = {"shortName": ticker, "returnOnEquity": .16,
                "revenueGrowth": .12, "profitMargins": .20,
                "earningsGrowth": .09, "fiftyTwoWeekChange": .08}
        if ticker == "MSFT":
            data["forwardPE"] = 24
        elif ticker == "AAPL":
            data["trailingPE"] = 18
        else:
            data["forwardPE"] = 30
        return data
    with patch("services.sector_value_screening_service._fetch_info", side_effect=fake_info):
        result = screen_sector("us", "technology")
    by_ticker = {row["ticker"]: row for row in result["results"]}
    assert by_ticker["AAPL"]["metrics"]["pe_basis"] == "trailing"
    assert by_ticker["AAPL"]["reference_comparison"]["pe"] is None
    assert by_ticker["CSCO"]["reference_comparison"]["pe"] == 6
    CACHE.clear()


def test_sector_reference_fetch_failure_remains_visible_without_comparison():
    CACHE.clear()
    def fake_info(ticker):
        if ticker == "MSFT":
            raise RuntimeError("temporary provider failure")
        return {"shortName": ticker, "forwardPE": 18,
                "returnOnEquity": .15, "revenueGrowth": .08,
                "profitMargins": .12}
    with patch("services.sector_value_screening_service._fetch_info", side_effect=fake_info):
        result = screen_sector("us", "technology")
    assert result["reference"]["ticker"] == "MSFT"
    assert result["reference"]["selection_method"] == "curated_first_ticker"
    assert result["reference"]["selection_verified"] is False
    assert result["reference"]["data_available"] is False
    assert result["reference"]["metrics"] is None
    assert "MSFT" in result["failures"]
    assert all(row["reference_comparison"]["pe"] is None for row in result["results"])
    CACHE.clear()


def test_us_semiconductors_is_industry_under_technology():
    CACHE.clear()
    def fake_info(ticker):
        return {"shortName": ticker, "forwardPE": 18, "priceToBook": 2,
                "returnOnEquity": .2, "revenueGrowth": .1, "profitMargins": .2}
    with patch("services.sector_value_screening_service._fetch_info", side_effect=fake_info):
        result = screen_sector("us", "semiconductors")
    assert result["classification_level"] == "industry"
    assert result["gics_sector_code"] == "45"
    assert result["industry_name"] == "Semiconductors"
    assert result["sample_size"] == 12
    assert result["semiconductor_cycle"]["status"] == "not_verified"
    assert all(row["valuation_label"] == "평가 보류" for row in result["results"])
