from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from database.models import InviteCode
import web.app as web_app


@pytest.fixture
def invite_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    InviteCode.__table__.create(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    next_id = {"value": 1}

    @event.listens_for(session_factory, "before_flush")
    def assign_id(session, *_):
        for row in session.new:
            if isinstance(row, InviteCode) and row.id is None:
                row.id = next_id["value"]
                next_id["value"] += 1

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

    monkeypatch.setattr(web_app, "get_db_session", isolated_session)
    return isolated_session


def _configure_supabase(monkeypatch, user_id=None):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "public-anon-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")

    created_user = SimpleNamespace(
        id=user_id or uuid4(),
        email="person@example.com",
    )
    fake_admin_client = SimpleNamespace(
        auth=SimpleNamespace(
            admin=SimpleNamespace(
                create_user=lambda payload: SimpleNamespace(user=created_user)
            )
        )
    )
    fake_public_client = SimpleNamespace(
        auth=SimpleNamespace(
            sign_in_with_password=lambda payload: SimpleNamespace(
                session=SimpleNamespace(
                    access_token="access-token",
                    refresh_token="refresh-token",
                )
            )
        )
    )

    def fake_create_client(url, key):
        if key == "service-role-key":
            return fake_admin_client
        assert key == "public-anon-key"
        return fake_public_client

    monkeypatch.setattr(web_app, "create_client", fake_create_client)
    return created_user


def _insert_invite(db, code, **kwargs):
    with db() as session:
        session.add(
            InviteCode(
                code_hash=web_app._invite_code_hash(code),
                **kwargs,
            )
        )


def test_invite_hash_is_normalized_and_not_plaintext():
    digest = web_app._invite_code_hash("  family-secret  ")
    assert digest == web_app._invite_code_hash("family-secret")
    assert digest != "family-secret"
    assert len(digest) == 64


def test_signup_rejects_unknown_invite(monkeypatch, invite_db):
    _configure_supabase(monkeypatch)
    with pytest.raises(HTTPException) as exc_info:
        web_app.signup_with_invite(
            web_app.SignupRequest(
                email="person@example.com",
                password="password123",
                invite_code="wrong-code",
            )
        )
    assert exc_info.value.status_code == 403


def test_signup_consumes_invite_once(monkeypatch, invite_db):
    created_user = _configure_supabase(monkeypatch)
    _insert_invite(invite_db, "correct-code")

    result = web_app.signup_with_invite(
        web_app.SignupRequest(
            email="person@example.com",
            password="password123",
            invite_code="correct-code",
        )
    )

    assert result["created"] is True
    assert result["access_token"] == "access-token"

    with invite_db() as session:
        invite = session.query(InviteCode).one()
        assert invite.used_at is not None
        assert invite.used_by == created_user.id

    with pytest.raises(HTTPException) as exc_info:
        web_app.signup_with_invite(
            web_app.SignupRequest(
                email="person@example.com",
                password="password123",
                invite_code="correct-code",
            )
        )
    assert exc_info.value.status_code == 403


def test_signup_rejects_expired_invite(monkeypatch, invite_db):
    _configure_supabase(monkeypatch)
    _insert_invite(
        invite_db,
        "expired-code",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    with pytest.raises(HTTPException) as exc_info:
        web_app.signup_with_invite(
            web_app.SignupRequest(
                email="person@example.com",
                password="password123",
                invite_code="expired-code",
            )
        )
    assert exc_info.value.status_code == 403


def test_signup_honors_intended_email(monkeypatch, invite_db):
    _configure_supabase(monkeypatch)
    _insert_invite(
        invite_db,
        "family-code",
        intended_email="allowed@example.com",
    )
    with pytest.raises(HTTPException) as exc_info:
        web_app.signup_with_invite(
            web_app.SignupRequest(
                email="person@example.com",
                password="password123",
                invite_code="family-code",
            )
        )
    assert exc_info.value.status_code == 403


def test_signup_ui_is_invite_only(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "public-anon-key")

    response = web_app.home()
    html = response.body.decode("utf-8")

    assert 'id="signup-form"' in html
    assert 'id="invite-code"' in html
    assert '"/api/auth/signup"' in html


def test_signup_requires_service_role_key(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "public-anon-key")
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)

    with pytest.raises(HTTPException) as exc_info:
        web_app.signup_with_invite(
            web_app.SignupRequest(
                email="person@example.com",
                password="password123",
                invite_code="correct-code",
            )
        )

    assert exc_info.value.status_code == 500


def test_admin_status_rejects_regular_user(monkeypatch, invite_db):
    user_id = uuid4()
    with invite_db() as session:
        # The invite-only fixture creates only invite_codes, so create profiles
        # explicitly for the authorization tests.
        web_app.Profile.__table__.create(session.get_bind(), checkfirst=True)
        session.add(web_app.Profile(id=user_id, is_admin=False))

    monkeypatch.setattr(
        web_app,
        "get_current_user",
        lambda authorization=None: {
            "authenticated": True,
            "user_id": str(user_id),
            "email": "member@example.com",
        },
    )

    with pytest.raises(HTTPException) as exc_info:
        web_app.get_admin_status("Bearer valid")
    assert exc_info.value.status_code == 403


def test_admin_status_accepts_admin(monkeypatch, invite_db):
    user_id = uuid4()
    with invite_db() as session:
        web_app.Profile.__table__.create(session.get_bind(), checkfirst=True)
        session.add(web_app.Profile(id=user_id, is_admin=True))

    monkeypatch.setattr(
        web_app,
        "get_current_user",
        lambda authorization=None: {
            "authenticated": True,
            "user_id": str(user_id),
            "email": "admin@example.com",
        },
    )

    result = web_app.get_admin_status("Bearer valid")
    assert result["is_admin"] is True
    assert result["user_id"] == str(user_id)
