"""Market-cap reference selection is limited to observed curated samples."""
from services import sector_value_screening_service as service


def _run(monkeypatch, caps):
    monkeypatch.setattr(service, "UNIVERSE", {"us": {"technology": list(caps)}})
    monkeypatch.setattr(service, "_fetch_info", lambda ticker: {
        "shortName": ticker, "forwardPE": 20, "returnOnEquity": .2,
        "revenueGrowth": .1, "marketCap": caps[ticker],
    })
    service.CACHE.clear()
    result = service.screen_sector("us", "technology")
    service.CACHE.clear()
    return result


def test_reference_is_largest_known_sample_market_cap(monkeypatch):
    result = _run(monkeypatch, {"AAA": 100, "BBB": 500, "CCC": None})
    assert result["reference"]["ticker"] == "BBB"
    assert result["reference"]["selection_method"] == "sample_market_cap_max"
    assert result["reference"]["selection_verified"] is False
    assert result["reference"]["market_cap_coverage"] == 2
    assert result["reference"]["market_cap_sample_size"] == 3


def test_reference_falls_back_when_market_caps_unavailable(monkeypatch):
    result = _run(monkeypatch, {"AAA": None, "BBB": None})
    assert result["reference"]["ticker"] == "AAA"
    assert result["reference"]["selection_method"] == "curated_first_ticker"
    assert result["reference"]["market_cap"] is None
