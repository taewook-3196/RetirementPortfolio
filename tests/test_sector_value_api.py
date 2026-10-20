"""Authentication and error boundaries for the read-only valuation endpoint."""
from unittest.mock import patch
from fastapi import HTTPException
import pytest
from web.app import get_sector_value_api


def test_sector_value_requires_authentication():
    with patch("web.app.get_verified_user_id", side_effect=HTTPException(status_code=401, detail="인증 필요")):
        with pytest.raises(HTTPException) as error:
            get_sector_value_api("us", "technology", authorization=None)
    assert error.value.status_code == 401


def test_sector_value_rejects_invalid_sector():
    with patch("web.app.get_verified_user_id", return_value="test-user"):
        with pytest.raises(HTTPException) as error:
            get_sector_value_api("us", "invalid", authorization="Bearer test")
    assert error.value.status_code == 400


def test_sector_value_returns_screening_data():
    payload = {"market": "us", "sector": "technology", "results": []}
    with patch("web.app.get_verified_user_id", return_value="test-user"), patch(
        "services.sector_value_screening_service.screen_sector", return_value=payload
    ):
        result = get_sector_value_api("us", "technology", authorization="Bearer test")
    assert result == payload


def test_sector_value_provider_error_does_not_leak_details():
    with patch("web.app.get_verified_user_id", return_value="test-user"), patch(
        "services.sector_value_screening_service.screen_sector", side_effect=RuntimeError("private provider token")
    ):
        with pytest.raises(HTTPException) as error:
            get_sector_value_api("us", "technology", authorization="Bearer test")
    assert error.value.status_code == 503
    assert "private provider token" not in error.value.detail


def test_sector_value_api_preserves_mobile_industry_contract(monkeypatch):
    """The endpoint must pass reference, coverage and peer data through unchanged."""
    from services import sector_value_screening_service as service

    monkeypatch.setattr(service, "UNIVERSE", {"us": {"technology": ["A", "B", "C"]}})
    records = {
        "A": {"industry": "Software", "marketCap": 100, "forwardPE": 10, "revenueGrowth": .1},
        "B": {"industry": "Software", "marketCap": 300, "forwardPE": 20, "revenueGrowth": .2},
        "C": {"industry": "Software", "marketCap": 200, "forwardPE": 30, "revenueGrowth": .3},
    }
    monkeypatch.setattr(service, "_fetch_info", lambda ticker: records[ticker])
    service.CACHE.clear()
    try:
        with patch("web.app.get_verified_user_id", return_value="test-user"):
            result = get_sector_value_api("us", "technology", authorization="Bearer test")
        assert result["reference"]["ticker"] == "B"
        assert result["reference"]["selection_method"] == "sample_market_cap_max"
        assert result["reference"]["selection_verified"] is False
        assert result["reference"]["basis"]
        coverage = result["industry_coverage"]
        assert coverage["classification_basis"] == "provider_industry_label"
        assert coverage["is_official_gics"] is False
        assert coverage["classified_count"] == coverage["sample_size"] == 3
        row = next(item for item in result["results"] if item["ticker"] == "A")
        peer = row["industry_peer_comparison"]
        assert peer["is_official_gics"] is False
        assert peer["metrics"]["forward_pe"]["peer_count"] == 3
        assert peer["metrics"]["forward_pe"]["peer_median"] == 20
        assert peer["metrics"]["forward_pe"]["difference"] == -10
    finally:
        service.CACHE.clear()
