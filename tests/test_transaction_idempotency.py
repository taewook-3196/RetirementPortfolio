"""Regression coverage for transaction write request IDs."""
from contextlib import contextmanager
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

import database.repository as repository_module
from database.models import Account, AssetMaster, Transaction


@pytest.fixture
def transaction_repo(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Account.__table__.create(engine)
    AssetMaster.__table__.create(engine)
    Transaction.__table__.create(engine)
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

    next_id = {"value": 0}

    def assign_id(session, flush_context, instances):
        for obj in session.new:
            if isinstance(obj, Transaction) and obj.id is None:
                next_id["value"] += 1
                obj.id = next_id["value"]

    event.listen(Session, "before_flush", assign_id)
    monkeypatch.setattr(repository_module, "init_db", lambda: None)
    monkeypatch.setattr(repository_module, "get_db_session", db_session)
    user_id = uuid4()
    with db_session() as session:
        session.add(Account(id=1, user_id=user_id, account_name="Test", currency="KRW"))
        session.add(AssetMaster(ticker="TEST", name="Test Asset", market="KR", currency="KRW"))
    yield repository_module.Repository(user_id=user_id), db_session
    event.remove(Session, "before_flush", assign_id)
    engine.dispose()


def save(repo, request_id, account_id=1, price=100):
    return repo.add_transaction(
        transaction_date="2026-10-08", ticker="TEST",
        transaction_type="BUY", quantity=2, price=price,
        account_id=account_id, request_id=request_id,
    )


def test_transaction_retry_returns_original(transaction_repo):
    repo, db_session = transaction_repo
    first = save(repo, "tx-request")
    second = save(repo, "tx-request")
    assert first.id == second.id
    with db_session() as session:
        assert session.query(Transaction).count() == 1


def test_transaction_new_request_creates_new_row(transaction_repo):
    repo, db_session = transaction_repo
    assert save(repo, "first").id != save(repo, "second").id
    with db_session() as session:
        assert session.query(Transaction).count() == 2


def test_transaction_replay_changed_price_rejected(transaction_repo):
    repo, db_session = transaction_repo
    save(repo, "same-id")
    with pytest.raises(ValueError, match="동일 요청 ID"):
        save(repo, "same-id", price=200)
    with db_session() as session:
        assert session.query(Transaction).count() == 1


def test_transaction_replay_other_account_rejected(transaction_repo):
    repo, db_session = transaction_repo
    save(repo, "shared-id")
    with db_session() as session:
        session.add(Account(id=2, user_id=repo.user_id, account_name="Other", currency="KRW"))
    with pytest.raises(ValueError, match="이미 사용된 요청 ID"):
        save(repo, "shared-id", account_id=2)
    with db_session() as session:
        assert session.query(Transaction).count() == 1


def test_transaction_replay_other_user_rejected(transaction_repo):
    repo, db_session = transaction_repo
    save(repo, "shared-user-id")
    other_user = uuid4()
    with db_session() as session:
        session.add(Account(id=3, user_id=other_user, account_name="Other user", currency="KRW"))
    other_repo = repository_module.Repository(user_id=other_user)
    with pytest.raises(ValueError, match="이미 사용된 요청 ID"):
        save(other_repo, "shared-user-id", account_id=3)
    with db_session() as session:
        assert session.query(Transaction).count() == 1
