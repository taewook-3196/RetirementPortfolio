from datetime import date, datetime

import pytest

from services.opening_snapshot_confirmation import check_opening_snapshot_confirmation


@pytest.mark.parametrize("opening_date", [date(2026, 1, 1), datetime(2026, 1, 1, 12, 30), "2026-01-01"])
def test_opening_date_accepts_iso_string_date_and_datetime(opening_date):
    snapshot = {"status": "draft", "opening_date": opening_date, "currency": "USD", "cash_amount": "0", "holdings": []}
    result = check_opening_snapshot_confirmation(snapshot)
    assert "INVALID_OPENING_DATE" not in {item["code"] for item in result["blockers"]}
    assert result["can_confirm"]


@pytest.mark.parametrize("opening_date", [None, 123, "invalid"])
def test_invalid_opening_dates_are_blocked_without_exception(opening_date):
    snapshot = {"status": "draft", "opening_date": opening_date, "currency": "USD", "cash_amount": "0", "holdings": []}
    result = check_opening_snapshot_confirmation(snapshot)
    assert "INVALID_OPENING_DATE" in {item["code"] for item in result["blockers"]}
