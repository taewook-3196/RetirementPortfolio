from datetime import date, timedelta
from services.pbr_band_service import calculate_pbr_band

def sample():
    start = date(2019, 1, 1)
    return [((start + timedelta(days=95 * i)).isoformat(), 0.7 + i * 0.02) for i in range(28)]

def test_requires_sufficient_history():
    assert calculate_pbr_band(sample()[:10], 1.0)["status"] == "withheld"
    assert calculate_pbr_band(sample()[:20], 1.0)["status"] == "withheld"

def test_valid_history_is_reference_only():
    result = calculate_pbr_band(sample(), 1.0)
    assert result["status"] == "reference_only"
    assert result["valid_count"] == 28
    assert result["band"]["p10"] <= result["band"]["median"] <= result["band"]["p90"]
    assert 0 <= result["historical_percentile"] <= 100

def test_invalid_and_future_values():
    assert calculate_pbr_band(sample(), 0)["status"] == "withheld"
    assert calculate_pbr_band(sample(), float("nan"))["status"] == "withheld"
    assert calculate_pbr_band(sample() + [("2099-01-01", 999)], 1.0)["valid_count"] == 28
