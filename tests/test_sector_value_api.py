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
