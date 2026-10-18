"""Repository-level opening snapshot isolation against a temporary SQLite database."""
from contextlib import contextmanager
from datetime import date
from decimal import Decimal

import pytest
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.schema import CreateTable
from sqlalchemy.orm import Session

from database.models import Account, AccountOpeningHolding, AccountOpeningSnapshot
from database import repository as repository_module


def test_opening_snapshot_repository_isolates_users(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    # SQLite autoincrements only INTEGER PRIMARY KEY, unlike PostgreSQL BIGINT.
    # Adapt only this test schema; leave production models untouched.
    with engine.begin() as connection:
        for table in (Account.__table__, AccountOpeningSnapshot.__table__, AccountOpeningHolding.__table__):
            ddl = str(CreateTable(table).compile(dialect=engine.dialect))
            ddl = ddl.replace("id BIGINT NOT NULL", "id INTEGER NOT NULL")
            connection.exec_driver_sql(ddl)

    owner_id, stranger_id = uuid4(), uuid4()
    with Session(engine) as session:
        session.add_all([
            Account(id=101, user_id=owner_id, account_name="Owner", currency="USD"),
            Account(id=202, user_id=stranger_id, account_name="Stranger", currency="USD"),
        ])
        session.commit()

    @contextmanager
    def isolated_session():
        with Session(engine) as session:
            yield session
            session.commit()

    monkeypatch.setattr(repository_module, "init_db", lambda: None)
    monkeypatch.setattr(repository_module, "get_db_session", isolated_session)
    owner = repository_module.Repository(user_id=owner_id)
    stranger = repository_module.Repository(user_id=stranger_id)
    kwargs = {
        "opening_date": date(2026, 1, 1),
        "cash_amount": "100", "currency": "USD",
        "holdings": [{"ticker": "AAPL", "quantity": "2", "market_value": "300"}],
    }

    assert owner.save_opening_snapshot_draft(101, **kwargs)["saved"]
    assert owner.get_opening_snapshot(101)["holdings"][0]["ticker"] == "AAPL"
    assert stranger.get_opening_snapshot(101) is None

    try:
        stranger.save_opening_snapshot_draft(101, **kwargs)
    except ValueError as exc:
        assert "계좌를 찾을 수 없습니다" in str(exc)
    else:
        raise AssertionError("Other user was able to overwrite owner's snapshot")

    assert Decimal(owner.get_opening_snapshot(101)["cash_amount"]) == Decimal("100")
    assert owner.get_opening_snapshot(202) is None
    assert stranger.get_opening_snapshot(202) is None
    engine.dispose()


def test_opening_snapshot_resave_replaces_holdings_and_confirmed_guard(monkeypatch):
    """A second draft save replaces holdings; confirmed data remains immutable."""
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        for table in (Account.__table__, AccountOpeningSnapshot.__table__, AccountOpeningHolding.__table__):
            ddl = str(CreateTable(table).compile(dialect=engine.dialect))
            connection.exec_driver_sql(ddl.replace("id BIGINT NOT NULL", "id INTEGER NOT NULL"))

    owner_id = uuid4()
    with Session(engine) as session:
        session.add(Account(id=303, user_id=owner_id, account_name="Resave", currency="USD"))
        session.commit()

    @contextmanager
    def isolated_session():
        with Session(engine) as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    monkeypatch.setattr(repository_module, "init_db", lambda: None)
    monkeypatch.setattr(repository_module, "get_db_session", isolated_session)
    owner = repository_module.Repository(user_id=owner_id)
    owner.save_opening_snapshot_draft(
        303, date(2026, 1, 1), "100", "USD",
        [{"ticker": "AAPL", "quantity": "2", "market_value": "300"}],
    )
    owner.save_opening_snapshot_draft(
        303, date(2026, 2, 1), "250", "USD",
        [{"ticker": "MSFT", "quantity": "1", "market_value": "500"}],
    )
    draft = owner.get_opening_snapshot(303)
    assert draft["opening_date"] == "2026-02-01"
    assert Decimal(draft["cash_amount"]) == Decimal("250")
    assert [item["ticker"] for item in draft["holdings"]] == ["MSFT"]

    with Session(engine) as session:
        snapshot = session.query(AccountOpeningSnapshot).filter_by(account_id=303).one()
        assert session.query(AccountOpeningHolding).filter_by(opening_snapshot_id=snapshot.id).count() == 1
        snapshot.status = "confirmed"
        session.commit()

    with pytest.raises(ValueError, match="확정된 시작 자산"):
        owner.save_opening_snapshot_draft(
            303, date(2026, 3, 1), "999", "USD",
            [{"ticker": "GOOG", "quantity": "5", "market_value": "999"}],
        )
    confirmed = owner.get_opening_snapshot(303)
    assert confirmed["status"] == "confirmed"
    assert confirmed["opening_date"] == "2026-02-01"
    assert Decimal(confirmed["cash_amount"]) == Decimal("250")
    assert [item["ticker"] for item in confirmed["holdings"]] == ["MSFT"]
    engine.dispose()
