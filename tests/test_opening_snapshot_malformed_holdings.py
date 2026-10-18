from services.opening_snapshot_confirmation import check_opening_snapshot_confirmation


def _snapshot(holdings):
    return {
        "status": "draft", "opening_date": "2026-01-01",
        "cash_amount": "0", "currency": "USD", "holdings": holdings,
    }


def test_missing_holdings_does_not_crash_preflight():
    result = check_opening_snapshot_confirmation(_snapshot(None))
    assert not result["can_confirm"]
    assert any(item["code"] == "INVALID_SNAPSHOT_VALUES" for item in result["blockers"])


def test_non_list_holdings_does_not_crash_preflight():
    result = check_opening_snapshot_confirmation(_snapshot({"ticker": "AAPL"}))
    assert not result["can_confirm"]
    assert any(item["code"] == "INVALID_SNAPSHOT_VALUES" for item in result["blockers"])


def test_valid_empty_holdings_are_allowed():
    result = check_opening_snapshot_confirmation(_snapshot([]))
    assert result["can_confirm"]
