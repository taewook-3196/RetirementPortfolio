from datetime import date

import pytest

from services.opening_snapshot_validation import validate_opening_snapshot


@pytest.mark.parametrize("holdings", [{"ticker": "AAPL"}, "AAPL", 5, True])
def test_non_list_holdings_are_rejected_without_exception(holdings):
    result = validate_opening_snapshot(date(2026, 1, 1), "0", "USD", holdings)
    assert not result["valid"]
    assert any("목록 형식" in error for error in result["errors"])


def test_empty_list_holdings_remain_valid():
    result = validate_opening_snapshot(date(2026, 1, 1), "0", "USD", [])
    assert result["valid"]
