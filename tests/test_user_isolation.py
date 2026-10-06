"""Task 12: prove that user-owned portfolio data cannot cross account boundaries."""

from contextlib import contextmanager
from datetime import date
from uuid import uuid4

from sqlalchemy import create_engine, event, JSON
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import sessionmaker

import database.repository as repository_module
from database.models import (
    Account,
    AssetMaster,
    InvestmentProfile,
    KakaoCredential,
    MorningReport,
    Transaction,
    UserSetting,
    Watchlist,
)
from database.repository import Repository


@compiles(ARRAY, "sqlite")
def compile_array_as_json(type_, compiler, **kw):
    return "JSON"


# ARRAY is PostgreSQL-specific. For these SQLite-only isolation tests, use
# JSON bind/result processing while keeping the production model unchanged.
InvestmentProfile.__table__.c.preferred_markets.type = JSON()
InvestmentProfile.__table__.c.excluded_assets.type = JSON()


def _isolated_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    for model in (
        Account,
        AssetMaster,
        Transaction,
        InvestmentProfile,
        UserSetting,
        Watchlist,
        MorningReport,
        KakaoCredential,
    ):
        model.__table__.create(engine)

    factory = sessionmaker(bind=engine, expire_on_commit=False)
    next_ids = {
        Account: 1,
        Transaction: 1,
        InvestmentProfile: 1,
        UserSetting: 1,
        Watchlist: 1,
        KakaoCredential: 1,
    }

    @event.listens_for(factory, "before_flush")
    def assign_ids(session, *_):
        for row in session.new:
            model = type(row)
            if model in next_ids and row.id is None:
                row.id = next_ids[model]
                next_ids[model] += 1

    @contextmanager
    def session_scope():
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
    monkeypatch.setattr(repository_module, "get_db_session", session_scope)
    return session_scope


def test_two_users_receive_independent_bootstrap_rows(monkeypatch):
    db = _isolated_db(monkeypatch)
    user_a, user_b = uuid4(), uuid4()

    assert Repository(user_id=user_a).ensure_user_initialized() == {
        "investment_profile_created": True,
        "user_settings_created": True,
    }
    assert Repository(user_id=user_b).ensure_user_initialized() == {
        "investment_profile_created": True,
        "user_settings_created": True,
    }

    with db() as session:
        assert session.query(InvestmentProfile).count() == 2
        assert session.query(UserSetting).count() == 2
        assert session.query(InvestmentProfile).filter_by(user_id=user_a).count() == 1
        assert session.query(InvestmentProfile).filter_by(user_id=user_b).count() == 1
        assert session.query(UserSetting).filter_by(user_id=user_a).count() == 1
        assert session.query(UserSetting).filter_by(user_id=user_b).count() == 1


def test_account_read_update_delete_are_owner_scoped(monkeypatch):
    db = _isolated_db(monkeypatch)
    user_a, user_b = uuid4(), uuid4()
    repo_a, repo_b = Repository(user_id=user_a), Repository(user_id=user_b)

    with db() as session:
        account_a = Account(user_id=user_a, account_name="A private account", is_default=True)
        account_b = Account(user_id=user_b, account_name="B private account", is_default=True)
        session.add_all([account_a, account_b])
        session.flush()
        account_a_id, account_b_id = account_a.id, account_b.id

    assert account_a_id != account_b_id

    assert [row.id for row in repo_a.get_accounts()] == [account_a_id]
    assert [row.id for row in repo_b.get_accounts()] == [account_b_id]
    assert repo_b.get_account(account_a_id) is None

    assert repo_b.update_account(
        account_a_id,
        account_name="hijacked",
        account_number="",
        broker="",
        initial_capital=0,
        base_monthly=0,
        max_additional_monthly=0,
        buy_cycle_type="monthly",
        buy_cycle_detail="25",
        currency="KRW",
        account_type="brokerage",
        market_scope="KR",
        contribution_type="none",
        contribution_amount=0,
        contribution_month=None,
        strategy_type="allocation",
        is_default=0,
        memo="",
    ) is False
    assert repo_b.delete_account(account_a_id) is False
    assert repo_a.get_account(account_a_id).account_name == "A private account"


def test_transaction_read_update_delete_are_owner_scoped(monkeypatch):
    db = _isolated_db(monkeypatch)
    user_a, user_b = uuid4(), uuid4()
    repo_a, repo_b = Repository(user_id=user_a), Repository(user_id=user_b)
    with db() as session:
        account_a = Account(user_id=user_a, account_name="A", is_default=True)
        account_b = Account(user_id=user_b, account_name="B", is_default=True)
        session.add_all([account_a, account_b])
        session.flush()
        account_a_id = account_a.id

    with db() as session:
        session.add(
            AssetMaster(
                ticker="TEST",
                name="Test Asset",
                market="US",
                asset_type="STOCK",
                currency="USD",
            )
        )

    tx = repo_a.add_transaction(
        transaction_date=date(2026, 10, 2),
        ticker="TEST",
        transaction_type="BUY",
        quantity=1,
        price=100,
        account_id=account_a_id,
    )

    assert repo_b.get_transactions(account_id=account_a_id) == []
    assert repo_b.update_transaction(
        tx.id,
        transaction_date=date(2026, 10, 2),
        ticker="TEST",
        transaction_type="BUY",
        quantity=2,
        price=100,
    ) is False
    assert repo_b.delete_transaction(tx.id) is False
    assert len(repo_a.get_transactions(account_id=account_a_id)) == 1


def test_user_settings_are_independent(monkeypatch):
    _isolated_db(monkeypatch)
    user_a, user_b = uuid4(), uuid4()
    repo_a, repo_b = Repository(user_id=user_a), Repository(user_id=user_b)
    repo_a.ensure_user_initialized()
    repo_b.ensure_user_initialized()

    repo_a.save_user_settings(
        morning_report_enabled=False,
        morning_report_time="06:30",
        kakao_enabled=True,
        news_enabled=False,
        ai_advice_enabled=False,
    )

    settings_a = repo_a.get_user_settings()
    settings_b = repo_b.get_user_settings()
    assert settings_a.morning_report_time.strftime("%H:%M") == "06:30"
    assert settings_a.kakao_enabled is True
    assert settings_b.morning_report_time.strftime("%H:%M") == "07:00"
    assert settings_b.kakao_enabled is False



def test_investment_profiles_are_owner_scoped(monkeypatch):
    _isolated_db(monkeypatch)
    user_a, user_b = uuid4(), uuid4()
    repo_a, repo_b = Repository(user_id=user_a), Repository(user_id=user_b)

    repo_a.save_investment_profile(
        risk_profile="aggressive",
        investment_preference_text="A private strategy",
    )
    repo_b.save_investment_profile(
        risk_profile="conservative",
        investment_preference_text="B private strategy",
    )

    assert repo_a.get_investment_profile().investment_preference_text == "A private strategy"
    assert repo_b.get_investment_profile().investment_preference_text == "B private strategy"


def test_watchlists_are_owner_scoped(monkeypatch):
    db = _isolated_db(monkeypatch)
    user_a, user_b = uuid4(), uuid4()
    repo_a, repo_b = Repository(user_id=user_a), Repository(user_id=user_b)
    with db() as session:
        session.add(
            AssetMaster(
                ticker="PRIVATE",
                name="Private Asset",
                market="US",
                asset_type="STOCK",
                currency="USD",
                is_active=True,
            )
        )

    repo_a.add_watchlist("PRIVATE", memo="A only")
    assert [row["ticker"] for row in repo_a.get_watchlist()] == ["PRIVATE"]
    assert repo_b.get_watchlist() == []
    assert repo_b.remove_watchlist("PRIVATE") is False
    assert [row["memo"] for row in repo_a.get_watchlist()] == ["A only"]


def test_morning_reports_are_owner_scoped(monkeypatch):
    _isolated_db(monkeypatch)
    user_a, user_b = uuid4(), uuid4()
    repo_a, repo_b = Repository(user_id=user_a), Repository(user_id=user_b)

    repo_a.upsert_morning_report("2026-10-06", "<p>A private report</p>")
    repo_b.upsert_morning_report("2026-10-06", "<p>B private report</p>")

    assert repo_a.get_latest_morning_report().html_content == "<p>A private report</p>"
    assert repo_b.get_latest_morning_report().html_content == "<p>B private report</p>"


def test_kakao_credentials_are_owner_scoped(monkeypatch):
    _isolated_db(monkeypatch)
    user_a, user_b = uuid4(), uuid4()
    repo_a, repo_b = Repository(user_id=user_a), Repository(user_id=user_b)

    repo_a.save_kakao_credential("enc-a-access", "enc-a-refresh", scopes="talk_message")
    repo_b.save_kakao_credential("enc-b-access", "enc-b-refresh", scopes="talk_message")

    assert repo_a.get_kakao_credential().access_token_encrypted == "enc-a-access"
    assert repo_b.get_kakao_credential().access_token_encrypted == "enc-b-access"

    assert repo_b.delete_kakao_credential() is True
    assert repo_b.get_kakao_credential() is None
    assert repo_a.get_kakao_credential().access_token_encrypted == "enc-a-access"
