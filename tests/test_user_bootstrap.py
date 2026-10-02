"""신규 사용자 기본 데이터 초기화를 검증합니다."""

from contextlib import contextmanager
from uuid import uuid4

from sqlalchemy import create_engine, event, JSON
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import sessionmaker

import database.repository as repository_module
from database.models import InvestmentProfile, UserSetting
from database.repository import Repository


@compiles(ARRAY, "sqlite")
def compile_array_as_json(type_, compiler, **kw):
    return "JSON"


# ARRAY is PostgreSQL-specific. For these SQLite-only isolation tests, use
# JSON bind/result processing while keeping the production model unchanged.
InvestmentProfile.__table__.c.preferred_markets.type = JSON()
InvestmentProfile.__table__.c.excluded_assets.type = JSON()


def test_user_bootstrap_is_idempotent(monkeypatch):
    engine = create_engine("sqlite:///:memory:")

    InvestmentProfile.__table__.create(engine)
    UserSetting.__table__.create(engine)

    session_factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )
    next_ids = {
        InvestmentProfile: 1,
        UserSetting: 1,
    }

    @event.listens_for(session_factory, "before_flush")
    def assign_ids(session, *_):
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

    monkeypatch.setattr(
        repository_module,
        "init_db",
        lambda: None,
    )
    monkeypatch.setattr(
        repository_module,
        "get_db_session",
        isolated_session,
    )

    user_id = uuid4()
    repo = Repository(user_id=user_id)

    first = repo.ensure_user_initialized()
    second = repo.ensure_user_initialized()

    assert first == {
        "investment_profile_created": True,
        "user_settings_created": True,
    }
    assert second == {
        "investment_profile_created": False,
        "user_settings_created": False,
    }

    with isolated_session() as session:
        profiles = (
            session.query(InvestmentProfile)
            .filter(
                InvestmentProfile.user_id
                == user_id
            )
            .all()
        )
        settings = (
            session.query(UserSetting)
            .filter(
                UserSetting.user_id
                == user_id
            )
            .all()
        )

        assert len(profiles) == 1
        assert len(settings) == 1
        assert (
            settings[0]
            .morning_report_time
            .strftime("%H:%M")
            == "07:00"
        )
