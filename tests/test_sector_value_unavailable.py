"""Provider outage must not look like valid neutral valuation."""
from unittest.mock import patch
import pytest
from services.sector_value_screening_service import CACHE, screen_sector


def test_all_fundamentals_missing_returns_error_and_does_not_cache():
    CACHE.clear()
    with patch("services.sector_value_screening_service._fetch_info", return_value={"shortName": "Name"}):
        with pytest.raises(RuntimeError, match="unavailable"):
            screen_sector("us", "technology")
    assert ("us", "technology") not in CACHE


def test_all_provider_requests_fail_returns_error():
    CACHE.clear()
    with patch("services.sector_value_screening_service._fetch_info", side_effect=TimeoutError):
        with pytest.raises(RuntimeError, match="unavailable"):
            screen_sector("us", "technology")
    assert ("us", "technology") not in CACHE
