"""Verify valuation API returns GICS metadata without external network calls."""
from services import sector_value_screening_service as service


def test_us_valuation_metadata(monkeypatch):
    monkeypatch.setattr(service, "UNIVERSE", {"us": {"technology": ["MSFT"]}})
    monkeypatch.setattr(service, "_fetch_info", lambda ticker: {
        "shortName": "Microsoft", "forwardPE": 25.0,
        "returnOnEquity": 0.2, "revenueGrowth": 0.1,
    })
    service.CACHE.clear()
    result = service.screen_sector("us", "technology")
    assert result["taxonomy"] == "GICS"
    assert result["gics_sector_code"] == "45"
    assert result["finviz_sector_label"] == "Technology"
    assert result["sample_size"] == 1
    assert result["pe_benchmark"]["valid_count"] == 1
    service.CACHE.clear()
