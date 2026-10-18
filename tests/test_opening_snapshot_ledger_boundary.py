"""Opening snapshot preflight must not silently absorb pre-opening ledger events."""
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from services.opening_snapshot_confirmation import check_opening_snapshot_confirmation


def snapshot(opening):
    return {
        "opening_date": opening.isoformat(),
        "status": "draft",
        "currency": "USD",
        "cash_amount": "100",
        "holdings": [{"ticker": "AAPL", "quantity": "2", "market_value": "200"}],
    }


@pytest.mark.parametrize(
    ("kind", "field"),
    [
        ("transactions", "transaction_date"),
        ("cash_flows", "flow_date"),
        ("dividends", "dividend_date"),
    ],
)
def test_preopening_event_blocks_confirmation(kind, field):
    opening = date.today() - timedelta(days=10)
    event = SimpleNamespace(**{field: opening - timedelta(days=1)})
    result = check_opening_snapshot_confirmation(
        snapshot(opening), **{kind: [event]}, account_currency="USD"
    )
    assert not result["can_confirm"]
    assert "EVENT_BEFORE_OPENING" in {item["code"] for item in result["blockers"]}


@pytest.mark.parametrize(
    ("kind", "field"),
    [
        ("transactions", "transaction_date"),
        ("cash_flows", "flow_date"),
        ("dividends", "dividend_date"),
    ],
)
def test_opening_day_event_requires_explicit_reconciliation(kind, field):
    opening = date.today() - timedelta(days=10)
    event = SimpleNamespace(**{field: opening})
    result = check_opening_snapshot_confirmation(
        snapshot(opening), **{kind: [event]}, account_currency="USD"
    )
    assert not result["can_confirm"]
    assert "EVENT_ON_OPENING_DATE" in {item["code"] for item in result["warnings"]}


def test_clean_opening_snapshot_has_no_ledger_warnings():
    opening = date.today() - timedelta(days=10)
    result = check_opening_snapshot_confirmation(snapshot(opening), account_currency="USD")
    assert result == {"can_confirm": True, "blockers": [], "warnings": []}
