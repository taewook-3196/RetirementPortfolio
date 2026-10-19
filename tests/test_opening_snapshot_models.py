"""Opening snapshot schema declarations remain opt-in and isolated from cash calculations."""
from database.models import (
    AccountOpeningHolding,
    AccountOpeningSnapshot,
    Base,
)


def test_opening_tables_have_isolated_names_and_columns():
    snapshot = AccountOpeningSnapshot.__table__
    holding = AccountOpeningHolding.__table__
    assert snapshot.name == "account_opening_snapshots"
    assert holding.name == "account_opening_holdings"
    assert {"account_id", "opening_date", "currency", "cash_amount", "status"} <= set(snapshot.columns.keys())
    assert {"opening_snapshot_id", "ticker", "quantity", "market_value"} <= set(holding.columns.keys())
    assert snapshot.name in Base.metadata.tables
    assert holding.name in Base.metadata.tables


def test_opening_snapshot_is_not_a_column_of_existing_accounts():
    assert "opening_date" not in Base.metadata.tables["accounts"].columns
    assert "opening_snapshot_id" not in Base.metadata.tables["transactions"].columns


def test_transaction_fx_columns_are_optional():
    columns = Base.metadata.tables['transactions'].columns
    for name in ('execution_fx_rate', 'settlement_amount', 'settlement_currency', 'fx_source'):
        assert columns[name].nullable
        assert columns[name].default is None


def test_transaction_fx_api_request_validates_optional_values():
    from datetime import date
    from pydantic import ValidationError
    from web.app import TransactionCreateRequest

    base = dict(transaction_date=date(2026, 10, 19), ticker="SPY", transaction_type="BUY", quantity=1, price=100)
    assert TransactionCreateRequest(**base).execution_fx_rate is None
    assert TransactionCreateRequest(**base, execution_fx_rate=1350, settlement_amount=135000, settlement_currency="KRW", fx_source="broker").settlement_currency == "KRW"
    for field, value in (("execution_fx_rate", 0), ("settlement_amount", -1), ("settlement_currency", "EUR"), ("fx_source", "unknown")):
        try:
            TransactionCreateRequest(**base, **{field: value})
        except ValidationError:
            continue
        raise AssertionError(f"Invalid {field} accepted")
