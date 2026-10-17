from datetime import date, timedelta
from services.opening_snapshot_validation import validate_opening_snapshot


def test_valid_opening_snapshot_does_not_change_input():
    holdings = [{"ticker": "spy", "quantity": "2", "market_value": "1000"}]
    result = validate_opening_snapshot(date(2025, 1, 1), "50000", "KRW", holdings)
    assert result["valid"]
    assert result["cash_amount"] == 50000
    assert result["holdings"][0]["ticker"] == "SPY"
    assert holdings[0]["ticker"] == "spy"


def test_rejects_invalid_opening_values():
    result = validate_opening_snapshot(
        date.today() + timedelta(days=1), "-1", "EUR",
        [{"ticker": "AAA", "quantity": "NaN", "market_value": "Infinity"},
         {"ticker": "AAA", "quantity": "1", "market_value": "10"}],
    )
    assert not result["valid"]
    assert len(result["errors"]) >= 4


def test_zero_quantity_cannot_have_nonzero_value():
    result = validate_opening_snapshot(date(2025, 1, 1), 0, "USD", [
        {"ticker": "QQQ", "quantity": 0, "market_value": 100}
    ])
    assert not result["valid"]
