"""Delivery-state regression tests for the existing report record API.

These tests document the current persistence semantics before introducing a
separate delivery attempt state machine. No production send is triggered.
"""
from contextlib import contextmanager
from datetime import date
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import database.repository as repository_module
from database.models import MorningReport
from database.repository import Repository


def test_delivery_record_is_scoped_to_owner_and_date(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    MorningReport.__table__.create(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    @contextmanager
    def session_scope():
        session = factory()
        try:
            yield session
            session.commit()
        finally:
            session.close()

    monkeypatch.setattr(repository_module, "get_db_session", session_scope)
    user_a, user_b = uuid4(), uuid4()
    a, b = object.__new__(Repository), object.__new__(Repository)
    a.user_id, b.user_id = user_a, user_b
    day = date(2026, 10, 12)
    a.upsert_morning_report(day, "owner A")
    b.upsert_morning_report(day, "owner B")

    assert a.mark_morning_report_kakao_sent(day) is True
    assert a.get_morning_report_for_date(day).kakao_sent_at is not None
    assert b.get_morning_report_for_date(day).kakao_sent_at is None
    assert a.mark_morning_report_kakao_sent(date(2026, 10, 11)) is False
    engine.dispose()


def test_updating_existing_report_does_not_clear_delivery_marker(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    MorningReport.__table__.create(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    @contextmanager
    def session_scope():
        session = factory()
        try:
            yield session
            session.commit()
        finally:
            session.close()

    monkeypatch.setattr(repository_module, "get_db_session", session_scope)
    repo = object.__new__(Repository)
    repo.user_id = uuid4()
    day = date(2026, 10, 12)
    repo.upsert_morning_report(day, "first")
    assert repo.mark_morning_report_kakao_sent(day)
    repo.upsert_morning_report(day, "regenerated")
    report = repo.get_morning_report_for_date(day)
    assert report.html_content == "regenerated"
    assert report.kakao_sent_at is not None
    engine.dispose()
