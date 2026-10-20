"""Peer median benchmarks must respect provider industries and sample limits."""
from services import sector_value_screening_service as service


def test_industry_peer_benchmarks_require_three_valid_observations(monkeypatch):
    monkeypatch.setattr(service, "UNIVERSE", {"us": {"technology": ["A", "B", "C", "D"]}})
    data = {
        "A": {"industry": "Software", "forwardPE": 10, "revenueGrowth": .1, "returnOnEquity": .2},
        "B": {"industry": "Software", "forwardPE": 20, "revenueGrowth": .2, "returnOnEquity": .3},
        "C": {"industry": "Software", "forwardPE": 30, "revenueGrowth": .3},
        "D": {"industry": "Hardware", "forwardPE": 50, "revenueGrowth": .9},
    }
    monkeypatch.setattr(service, "_fetch_info", lambda ticker: data[ticker])
    service.CACHE.clear()
    result = service.screen_sector("us", "technology")
    benchmarks = result["industry_coverage"]["benchmarks"]
    assert benchmarks["Software"]["forward_pe"]["median"] == 20
    assert benchmarks["Software"]["revenue_growth"]["median"] == .2
    assert benchmarks["Software"]["roe"]["median"] is None
    assert benchmarks["Software"]["roe"]["valid_count"] == 2
    assert benchmarks["Hardware"]["forward_pe"]["median"] is None
    assert result["industry_coverage"]["is_official_gics"] is False
    service.CACHE.clear()
