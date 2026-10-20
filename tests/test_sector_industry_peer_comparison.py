"""Company peer comparisons must use same provider industry only."""
from services import sector_value_screening_service as service


def test_company_industry_peer_differences(monkeypatch):
    monkeypatch.setattr(service, "UNIVERSE", {"us": {"technology": ["A", "B", "C", "D"]}})
    data = {
        "A": {"industry": "Software", "forwardPE": 10, "revenueGrowth": .1},
        "B": {"industry": "Software", "forwardPE": 20, "revenueGrowth": .2},
        "C": {"industry": "Software", "forwardPE": 30, "revenueGrowth": .3},
        "D": {"industry": "Hardware", "forwardPE": 50, "revenueGrowth": .9},
    }
    monkeypatch.setattr(service, "_fetch_info", lambda ticker: data[ticker])
    service.CACHE.clear()
    result = service.screen_sector("us", "technology")
    rows = {row["ticker"]: row["industry_peer_comparison"] for row in result["results"]}
    assert rows["A"]["metrics"]["forward_pe"]["peer_median"] == 20
    assert rows["A"]["metrics"]["forward_pe"]["difference"] == -10
    assert rows["C"]["metrics"]["revenue_growth"]["difference"] == .1
    assert rows["D"]["metrics"]["forward_pe"]["peer_median"] is None
    assert rows["D"]["metrics"]["forward_pe"]["difference"] is None
    assert rows["A"]["is_official_gics"] is False
    service.CACHE.clear()


def test_peer_median_includes_subject_and_rejects_invalid_forward_pe(monkeypatch):
    monkeypatch.setattr(service, "UNIVERSE", {"us": {"technology": ["A", "B", "C", "D"]}})
    data = {
        "A": {"industry": "Software", "forwardPE": 10, "revenueGrowth": .1},
        "B": {"industry": "Software", "forwardPE": 20, "revenueGrowth": .2},
        "C": {"industry": "Software", "forwardPE": 0, "revenueGrowth": .3},
        "D": {"industry": "Software", "forwardPE": 250, "revenueGrowth": .4},
    }
    monkeypatch.setattr(service, "_fetch_info", lambda ticker: data[ticker])
    service.CACHE.clear()
    try:
        result = service.screen_sector("us", "technology")
        rows = {row["ticker"]: row["industry_peer_comparison"]["metrics"] for row in result["results"]}
        assert rows["A"]["revenue_growth"]["peer_count"] == 4
        assert rows["A"]["revenue_growth"]["peer_median"] == .25
        assert rows["A"]["revenue_growth"]["difference"] == -.15
        assert rows["A"]["forward_pe"]["peer_count"] == 2
        assert rows["A"]["forward_pe"]["peer_median"] is None
        assert rows["A"]["forward_pe"]["difference"] is None
        assert rows["C"]["forward_pe"]["value"] is None
        assert rows["D"]["forward_pe"]["value"] is None
    finally:
        service.CACHE.clear()
