"""사용자 소유권과 쓰기 입력 검증을 격리 DB에서 확인합니다."""

from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import database.repository as repository_module
from database.models import (
    Account,
    AccountTarget,
    AssetMaster,
    CashFlow,
    Dividend,
    Transaction,
)
from database.repository import Repository


@pytest.fixture()
def isolated_repositories(monkeypatch):
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    for table in (
        Account.__table__,
        AssetMaster.__table__,
        AccountTarget.__table__,
        CashFlow.__table__,
        Transaction.__table__,
        Dividend.__table__,
    ):
        table.create(engine)

    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    next_ids = {
        Transaction: 1,
        CashFlow: 1,
        Dividend: 1,
        AccountTarget: 1,
    }

    @event.listens_for(session_factory, "before_flush")
    def assign_sqlite_bigint_ids(session, *_):
        # PostgreSQL BIGSERIAL과 달리 SQLite는 BIGINT PK를 자동 증가시키지 않습니다.
        for row in session.new:
            model = type(row)
            if model in next_ids and row.id is None:
                row.id = next_ids[model]
                next_ids[model] += 1

    @contextmanager
    def isolated_session():
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr(repository_module, "init_db", lambda: None)
    monkeypatch.setattr(repository_module, "get_db_session", isolated_session)

    user_a = uuid4()
    user_b = uuid4()
    with isolated_session() as session:
        session.add(
            AssetMaster(
                ticker="AAA",
                name="검증 종목",
                market="KR",
                currency="KRW",
                is_active=True,
            )
        )
        session.add_all(
            [
                Account(
                    id=1,
                    user_id=user_a,
                    account_name="A 계좌",
                    currency="KRW",
                    is_default=True,
                ),
                Account(
                    id=2,
                    user_id=user_b,
                    account_name="B 계좌",
                    currency="KRW",
                    is_default=True,
                ),
            ]
        )

    return SimpleNamespace(
        repo_a=Repository(user_id=str(user_a)),
        repo_b=Repository(user_id=str(user_b)),
        session=isolated_session,
    )


def test_other_user_account_read_update_and_delete_are_hidden(
    isolated_repositories,
):
    repo_a = isolated_repositories.repo_a

    assert repo_a.get_account(2) is None
    assert repo_a.update_account(2, account_name="침범") is False
    assert repo_a.delete_account(2) is False
    assert isolated_repositories.repo_b.get_account(2).account_name == "B 계좌"


def test_other_user_transaction_update_delete_and_chart_are_hidden(
    isolated_repositories,
):
    repo_b = isolated_repositories.repo_b
    transaction = repo_b.add_transaction(
        "2026-01-02", "AAA", "BUY", 3, 100, account_id=2
    )
    repo_a = isolated_repositories.repo_a

    assert repo_a.get_transactions(account_id=2) == []
    assert repo_a.update_transaction(
        transaction.id, "2026-01-03", "AAA", "BUY", 1, 100, account_id=1
    ) is False
    assert repo_a.delete_transaction(transaction.id) is False
    assert repo_a.get_asset_chart_data(2, "AAA") == {
        "prices": [],
        "transactions": [],
    }
    assert len(repo_b.get_transactions(account_id=2)) == 1


def test_other_user_cash_flow_update_and_delete_are_hidden(
    isolated_repositories,
):
    repo_b = isolated_repositories.repo_b
    cash_flow = repo_b.create_cash_flow(
        2, "2026-01-02", "DEPOSIT", 1000, "KRW"
    )
    repo_a = isolated_repositories.repo_a

    assert repo_a.get_cash_flows(2) == []
    assert repo_a.update_cash_flow(
        cash_flow.id, "2026-01-03", "WITHDRAWAL", 10, "KRW"
    ) is False
    assert repo_a.delete_cash_flow(cash_flow.id) is False
    assert len(repo_b.get_cash_flows(2)) == 1


def test_other_user_targets_and_dividends_are_hidden(
    isolated_repositories,
):
    with isolated_repositories.session() as session:
        session.add_all(
            [
                AccountTarget(
                    account_id=2,
                    ticker="AAA",
                    target_weight=100,
                    dividend_yield=0,
                ),
                Dividend(
                    account_id=2,
                    dividend_date=date(2026, 1, 3),
                    ticker="AAA",
                    currency="KRW",
                    gross_amount=10,
                    tax=1,
                    net_amount=9,
                ),
            ]
        )

    repo_a = isolated_repositories.repo_a
    assert repo_a.get_account_targets(account_id=2) == []
    assert repo_a.get_dividends(account_id=2) == []


@pytest.mark.parametrize("transaction_type", ["", "HOLD", "DEPOSIT"])
def test_invalid_transaction_type_is_rejected(
    isolated_repositories,
    transaction_type,
):
    with pytest.raises(ValueError, match="BUY 또는 SELL"):
        isolated_repositories.repo_a.add_transaction(
            "2026-01-02", "AAA", transaction_type, 1, 100, account_id=1
        )


@pytest.mark.parametrize("quantity", [0, -1])
def test_non_positive_transaction_quantity_is_rejected(
    isolated_repositories,
    quantity,
):
    with pytest.raises(ValueError, match="거래 수량"):
        isolated_repositories.repo_a.add_transaction(
            "2026-01-02", "AAA", "BUY", quantity, 100, account_id=1
        )


@pytest.mark.parametrize("price", [0, -1])
def test_non_positive_transaction_price_is_rejected(
    isolated_repositories,
    price,
):
    with pytest.raises(ValueError, match="거래 가격"):
        isolated_repositories.repo_a.add_transaction(
            "2026-01-02", "AAA", "BUY", 1, price, account_id=1
        )


@pytest.mark.parametrize(
    ("fee", "tax", "message"),
    [(-1, 0, "수수료"), (0, -1, "세금")],
)
def test_negative_transaction_cost_is_rejected(
    isolated_repositories,
    fee,
    tax,
    message,
):
    with pytest.raises(ValueError, match=message):
        isolated_repositories.repo_a.add_transaction(
            "2026-01-02",
            "AAA",
            "BUY",
            1,
            100,
            fee=fee,
            tax=tax,
            account_id=1,
        )


def test_empty_ticker_and_invalid_transaction_date_are_rejected(
    isolated_repositories,
):
    repo = isolated_repositories.repo_a
    with pytest.raises(ValueError, match="종목코드"):
        repo.add_transaction("2026-01-02", "  ", "BUY", 1, 100, account_id=1)
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        repo.add_transaction("2026-02-30", "AAA", "BUY", 1, 100, account_id=1)


def test_oversell_and_update_that_would_make_holdings_negative_are_rejected(
    isolated_repositories,
):
    repo = isolated_repositories.repo_a
    buy = repo.add_transaction(
        "2026-01-02", "AAA", "BUY", 5, 100, account_id=1
    )
    repo.add_transaction("2026-01-03", "AAA", "SELL", 2, 110, account_id=1)

    with pytest.raises(ValueError, match="보유수량"):
        repo.add_transaction("2026-01-04", "AAA", "SELL", 4, 110, account_id=1)
    with pytest.raises(ValueError, match="보유수량"):
        repo.update_transaction(
            buy.id, "2026-01-02", "AAA", "BUY", 1, 100, account_id=1
        )


def test_normal_buy_and_sell_are_saved_with_validated_values(
    isolated_repositories,
):
    repo = isolated_repositories.repo_a
    buy = repo.add_transaction(
        date(2026, 1, 2), " aaa ", "buy", 5, 100, fee=1, tax=2, account_id=1
    )
    sell = repo.add_transaction(
        "2026-01-03", "AAA", "SELL", 2, 110, fee=1, tax=1, account_id=1
    )

    assert (buy.ticker, buy.transaction_type, float(buy.price)) == (
        "AAA", "BUY", 100.0
    )
    assert (sell.transaction_type, float(sell.quantity)) == ("SELL", 2.0)


@pytest.mark.parametrize("flow_type", ["", "BUY", "TRANSFER"])
def test_invalid_cash_flow_type_is_rejected(
    isolated_repositories,
    flow_type,
):
    with pytest.raises(ValueError, match="DEPOSIT 또는 WITHDRAWAL"):
        isolated_repositories.repo_a.create_cash_flow(
            1, "2026-01-02", flow_type, 100, "KRW"
        )


@pytest.mark.parametrize("amount", [0, -100])
def test_non_positive_cash_flow_amount_is_rejected(
    isolated_repositories,
    amount,
):
    with pytest.raises(ValueError, match="입출금 금액"):
        isolated_repositories.repo_a.create_cash_flow(
            1, "2026-01-02", "DEPOSIT", amount, "KRW"
        )


def test_cash_flow_date_and_account_currency_are_validated(
    isolated_repositories,
):
    repo = isolated_repositories.repo_a
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        repo.create_cash_flow(1, "not-a-date", "DEPOSIT", 100, "KRW")
    with pytest.raises(ValueError, match="계좌 통화"):
        repo.create_cash_flow(1, "2026-01-02", "DEPOSIT", 100, "USD")


def test_normal_deposit_and_withdrawal_are_saved(
    isolated_repositories,
):
    repo = isolated_repositories.repo_a
    deposit = repo.create_cash_flow(
        1, "2026-01-02", "deposit", 1000, "krw"
    )
    withdrawal = repo.create_cash_flow(
        1, date(2026, 1, 3), "WITHDRAWAL", 250, "KRW"
    )

    assert (deposit.flow_type, float(deposit.amount), deposit.currency) == (
        "DEPOSIT", 1000.0, "KRW"
    )
    assert (withdrawal.flow_type, float(withdrawal.amount)) == (
        "WITHDRAWAL", 250.0
    )


def test_updates_apply_the_same_transaction_and_cash_flow_validation(
    isolated_repositories,
):
    repo = isolated_repositories.repo_a
    transaction = repo.add_transaction(
        "2026-01-02", "AAA", "BUY", 2, 100, account_id=1
    )
    cash_flow = repo.create_cash_flow(
        1, "2026-01-02", "DEPOSIT", 100, "KRW"
    )

    with pytest.raises(ValueError, match="수수료"):
        repo.update_transaction(
            transaction.id,
            "2026-01-02",
            "AAA",
            "BUY",
            2,
            100,
            fee=-1,
            account_id=1,
        )
    with pytest.raises(ValueError, match="입출금 금액"):
        repo.update_cash_flow(
            cash_flow.id, "2026-01-02", "DEPOSIT", 0, "KRW"
        )


def test_account_delete_cascades_only_owned_related_rows(
    isolated_repositories,
):
    repo_a = isolated_repositories.repo_a
    repo_b = isolated_repositories.repo_b
    repo_a.add_transaction("2026-01-02", "AAA", "BUY", 1, 100, account_id=1)
    repo_a.create_cash_flow(1, "2026-01-02", "DEPOSIT", 100, "KRW")

    with isolated_repositories.session() as session:
        session.add_all(
            [
                Dividend(
                    id=1,
                    account_id=1,
                    dividend_date=date(2026, 1, 3),
                    ticker="AAA",
                    currency="KRW",
                    gross_amount=10,
                    tax=1,
                    net_amount=9,
                ),
                AccountTarget(
                    id=1,
                    account_id=1,
                    ticker="AAA",
                    target_weight=100,
                    dividend_yield=0,
                ),
            ]
        )

    assert repo_b.delete_account(1) is False
    assert repo_a.delete_account(1) is True

    with isolated_repositories.session() as session:
        assert session.query(Transaction).filter_by(account_id=1).count() == 0
        assert session.query(CashFlow).filter_by(account_id=1).count() == 0
        assert session.query(Dividend).filter_by(account_id=1).count() == 0
        assert session.query(AccountTarget).filter_by(account_id=1).count() == 0
        assert session.query(Account).filter_by(id=2).count() == 1
