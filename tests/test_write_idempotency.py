"""Regression tests for cash-flow write idempotency."""
from contextlib import contextmanager
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import database.repository as repository_module
from database.models import Account, CashFlow


@pytest.fixture
def repo_and_session(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Account.__table__.create(engine)
    CashFlow.__table__.create(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    @contextmanager
    def db_session():
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr(repository_module, "init_db", lambda: None)
    monkeypatch.setattr(repository_module, "get_db_session", db_session)
    user_id = uuid4()
    with db_session() as session:
        session.add(Account(id=1, user_id=user_id, account_name="Test", currency="KRW"))
    return repository_module.Repository(user_id=user_id), db_session


def write(repo, request_id, amount=100):
    return repo.create_cash_flow(
        account_id=1, flow_date="2026-10-08", flow_type="DEPOSIT",
        amount=amount, currency="KRW", request_id=request_id,
    )


def test_retry_returns_same_cash_flow(repo_and_session):
    repo, db_session = repo_and_session
    first = write(repo, "request-1")
    second = write(repo, "request-1")
    assert first.id == second.id
    with db_session() as session:
        assert session.query(CashFlow).count() == 1


def test_new_request_allows_same_amount(repo_and_session):
    repo, db_session = repo_and_session
    assert write(repo, "request-1").id != write(repo, "request-2").id
    with db_session() as session:
        assert session.query(CashFlow).count() == 2


def test_reused_request_rejects_changed_amount(repo_and_session):
    repo, db_session = repo_and_session
    write(repo, "request-1")
    with pytest.raises(ValueError, match="동일 요청 ID"):
        write(repo, "request-1", amount=200)
    with db_session() as session:
        assert session.query(CashFlow).count() == 1
