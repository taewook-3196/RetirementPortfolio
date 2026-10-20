"""Industry label grouping must not masquerade as official GICS data."""
from services import sector_value_screening_service as service


def test_provider_industry_coverage_and_missing_labels(monkeypatch):
    monkeypatch.setattr(service, "UNIVERSE", {"us": {"technology": ["A", "B", "C"]}})
    data = {
        "A": {"forwardPE": 20, "industry": "Software - Infrastructure"},
        "B": {"forwardPE": 22, "industry": "Software - Infrastructure"},
        "C": {"forwardPE": 19},
    }
    monkeypatch.setattr(service, "_fetch_info", lambda ticker: data[ticker])
    service.CACHE.clear()
    result = service.screen_sector("us", "technology")
    coverage = result["industry_coverage"]
    assert coverage["is_official_gics"] is False
    assert coverage["classified_count"] == 2
    assert coverage["sample_size"] == 3
    assert coverage["groups"] == [{
        "industry": "Software - Infrastructure",
        "ticker_count": 2, "tickers": ["A", "B"]
    }]
    service.CACHE.clear()
