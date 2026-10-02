"""Task 13 tests for scheduled multi-user morning report discovery."""

from contextlib import contextmanager
from datetime import time
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import database.repository as repository_module
from database.models import UserSetting
from database.repository import Repository


def test_only_enabled_report_users_are_discovered(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    UserSetting.__table__.create(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    @contextmanager
    def session_scope():
        session = factory()
        try:
            yield session
            session.commit()
        finally:
            session.close()

    monkeypatch.setattr(repository_module, "init_db", lambda: None)
    monkeypatch.setattr(repository_module, "get_db_session", session_scope)

    enabled_user = uuid4()
    disabled_user = uuid4()
    with session_scope() as session:
        session.add_all([
            UserSetting(
                user_id=enabled_user,
                morning_report_enabled=True,
                morning_report_time=time(7, 0),
                kakao_enabled=False,
                news_enabled=True,
                ai_advice_enabled=True,
            ),
            UserSetting(
                user_id=disabled_user,
                morning_report_enabled=False,
                morning_report_time=time(7, 0),
                kakao_enabled=False,
                news_enabled=True,
                ai_advice_enabled=True,
            ),
        ])

    assert Repository.get_morning_report_user_ids() == [enabled_user]
