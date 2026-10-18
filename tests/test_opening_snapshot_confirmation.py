"""Tests for conservative opening snapshot confirmation checks."""
from datetime import date
from types import SimpleNamespace

from services.opening_snapshot_confirmation import check_opening_snapshot_confirmation


def _snapshot():
    return {"status": "draft", "opening_date": "2026-01-01", "currency": "USD", "cash_amount": "0", "holdings": [{"ticker": "AAPL", "quantity": "2", "market_value": "300"}]}


def test_empty_draft_can_proceed_to_future_confirmation_step():
    result = check_opening_snapshot_confirmation(_snapshot())
    assert result["can_confirm"] is True
    assert result["blockers"] == []
    assert result["warnings"] == []


def test_preopening_transaction_blocks_confirmation():
    trade = SimpleNamespace(transaction_date=date(2025, 12, 31), ticker="AAPL")
    result = check_opening_snapshot_confirmation(_snapshot(), transactions=[trade])
    assert result["can_confirm"] is False
    assert any(item["code"] == "EVENT_BEFORE_OPENING" for item in result["blockers"])


def test_overlap_warns_and_requires_reconciliation():
    trade = SimpleNamespace(transaction_date=date(2026, 2, 1), ticker="AAPL")
    result = check_opening_snapshot_confirmation(_snapshot(), transactions=[trade])
    assert result["can_confirm"] is False
    assert any(item["code"] == "OPENING_TRADE_OVERLAP" for item in result["warnings"])


def test_invalid_event_date_blocks_confirmation():
    result = check_opening_snapshot_confirmation(_snapshot(), cash_flows=[SimpleNamespace(flow_date=None)])
    assert result["can_confirm"] is False
    assert any(item["code"] == "INVALID_EVENT_DATE" for item in result["blockers"])


def test_missing_and_confirmed_snapshot_cannot_confirm():
    assert not check_opening_snapshot_confirmation(None)["can_confirm"]
    confirmed = {**_snapshot(), "status": "confirmed"}
    assert not check_opening_snapshot_confirmation(confirmed)["can_confirm"]


def test_same_day_event_requires_reconciliation():
    flow = SimpleNamespace(flow_date=date(2026, 1, 1))
    result = check_opening_snapshot_confirmation(_snapshot(), cash_flows=[flow])
    assert result["can_confirm"] is False
    assert any(item["code"] == "EVENT_ON_OPENING_DATE" for item in result["warnings"])


def test_future_opening_date_blocks_confirmation():
    future = {**_snapshot(), "opening_date": "2999-01-01"}
    result = check_opening_snapshot_confirmation(future)
    assert result["can_confirm"] is False
    assert any(item["code"] == "FUTURE_OPENING_DATE" for item in result["blockers"])


def test_invalid_persisted_cash_blocks_confirmation():
    bad = {**_snapshot(), "cash_amount": "-10"}
    result = check_opening_snapshot_confirmation(bad)
    assert result["can_confirm"] is False
    assert any(item["code"] == "INVALID_SNAPSHOT_VALUES" for item in result["blockers"])


def test_invalid_persisted_holdings_block_confirmation():
    bad = {**_snapshot(), "holdings": [{"ticker": "AAPL", "quantity": "-1", "market_value": "100"}]}
    result = check_opening_snapshot_confirmation(bad)
    assert result["can_confirm"] is False
    assert any(item["code"] == "INVALID_SNAPSHOT_VALUES" for item in result["blockers"])


def test_invalid_currency_blocks_confirmation():
    bad = {**_snapshot(), "currency": "EUR"}
    result = check_opening_snapshot_confirmation(bad)
    assert result["can_confirm"] is False
    assert any(item["code"] == "INVALID_SNAPSHOT_VALUES" for item in result["blockers"])


def test_account_currency_mismatch_blocks_confirmation():
    result = check_opening_snapshot_confirmation(_snapshot(), account_currency="KRW")
    assert result["can_confirm"] is False
    assert any(item["code"] == "ACCOUNT_CURRENCY_MISMATCH" for item in result["blockers"])


def test_matching_account_currency_does_not_block_confirmation():
    result = check_opening_snapshot_confirmation(_snapshot(), account_currency="USD")
    assert result["can_confirm"] is True


def test_sell_exceeding_opening_quantity_blocks_confirmation():
    trade = SimpleNamespace(
        id=1, transaction_date=date(2026, 1, 2),
        ticker="AAPL", transaction_type="SELL", quantity="5",
    )
    snapshot = {**_snapshot(), "holdings": [
        {"ticker": "AAPL", "quantity": "2", "market_value": "200"}
    ]}
    result = check_opening_snapshot_confirmation(snapshot, transactions=[trade])
    assert result["can_confirm"] is False
    assert any(item["code"] == "NEGATIVE_RECONCILED_POSITION" for item in result["blockers"])


def test_buy_before_sell_avoids_negative_position_blocker():
    trades = [
        SimpleNamespace(id=1, transaction_date=date(2026, 1, 2), ticker="AAPL", transaction_type="BUY", quantity="4"),
        SimpleNamespace(id=2, transaction_date=date(2026, 1, 3), ticker="AAPL", transaction_type="SELL", quantity="5"),
    ]
    snapshot = {**_snapshot(), "holdings": [
        {"ticker": "AAPL", "quantity": "2", "market_value": "200"}
    ]}
    result = check_opening_snapshot_confirmation(snapshot, transactions=trades)
    assert not any(item["code"] == "NEGATIVE_RECONCILED_POSITION" for item in result["blockers"])


def test_invalid_trade_quantity_blocks_confirmation():
    trade = SimpleNamespace(id=1, transaction_date=date(2026, 1, 2), ticker="AAPL", transaction_type="SELL", quantity="NaN")
    result = check_opening_snapshot_confirmation(_snapshot(), transactions=[trade])
    assert any(item["code"] == "INVALID_TRADE_QUANTITY" for item in result["blockers"])
