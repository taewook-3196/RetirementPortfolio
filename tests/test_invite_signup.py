from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import AppSetting, Profile, KakaoCredential, UserSetting
import web.app as web_app


@pytest.fixture
def membership_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    for table in (Profile, AppSetting, KakaoCredential, UserSetting):
        table.__table__.create(engine, checkfirst=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

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

    monkeypatch.setattr(web_app, "get_db_session", session_scope)
    return session_scope


def _configure_signup(monkeypatch, user_id=None):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "public-anon-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    user = SimpleNamespace(id=user_id or uuid4(), email="person@example.com")
    admin = SimpleNamespace(auth=SimpleNamespace(admin=SimpleNamespace(
        create_user=lambda payload: SimpleNamespace(user=user)
    )))
    public = SimpleNamespace(auth=SimpleNamespace(
        sign_in_with_password=lambda payload: SimpleNamespace(session=SimpleNamespace(
            access_token="access-token", refresh_token="refresh-token"
        ))
    ))
    monkeypatch.setattr(web_app, "create_client", lambda url, key: admin if key == "service-role-key" else public)
    return user


def test_signup_is_closed_by_default(membership_db):
    assert web_app.get_signup_status() == {"signup_enabled": False}


def test_admin_can_enable_and_disable_signup(monkeypatch, membership_db):
    monkeypatch.setattr(web_app, "require_admin", lambda authorization=None: {"user_id": str(uuid4())})
    assert web_app.set_signup_status(web_app.SignupControlRequest(enabled=True), "Bearer admin")["signup_enabled"] is True
    assert web_app.get_signup_status()["signup_enabled"] is True
    assert web_app.set_signup_status(web_app.SignupControlRequest(enabled=False), "Bearer admin")["signup_enabled"] is False


def test_signup_rejected_when_closed(monkeypatch, membership_db):
    _configure_signup(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        web_app.signup(web_app.SignupRequest(email="person@example.com", password="password123"))
    assert exc.value.status_code == 403


def test_signup_succeeds_when_enabled_and_creates_active_profile(monkeypatch, membership_db):
    user = _configure_signup(monkeypatch)
    with membership_db() as db:
        db.add(AppSetting(key="signup_enabled", value="true"))
    result = web_app.signup(web_app.SignupRequest(email="person@example.com", password="password123"))
    assert result["created"] is True
    assert result["access_token"] == "access-token"
    with membership_db() as db:
        profile = db.query(Profile).filter(Profile.id == user.id).one()
        assert profile.is_active is True
        assert profile.is_admin is False


def test_admin_cannot_suspend_self(monkeypatch, membership_db):
    admin_id = uuid4()
    monkeypatch.setattr(web_app, "require_admin", lambda authorization=None: {"user_id": str(admin_id)})
    with pytest.raises(HTTPException) as exc:
        web_app.set_member_access(admin_id, web_app.MemberAccessRequest(active=False), "Bearer admin")
    assert exc.value.status_code == 400


def test_admin_can_suspend_and_reactivate_member(monkeypatch, membership_db):
    admin_id, member_id = uuid4(), uuid4()
    monkeypatch.setattr(web_app, "require_admin", lambda authorization=None: {"user_id": str(admin_id)})
    with membership_db() as db:
        db.add(Profile(id=member_id, is_admin=False, is_active=True))
    assert web_app.set_member_access(member_id, web_app.MemberAccessRequest(active=False), "Bearer admin")["is_active"] is False
    with membership_db() as db:
        assert db.query(Profile).filter(Profile.id == member_id).one().is_active is False
    assert web_app.set_member_access(member_id, web_app.MemberAccessRequest(active=True), "Bearer admin")["is_active"] is True


def test_admin_member_response_exposes_only_operational_fields(monkeypatch, membership_db):
    member_id = uuid4()
    fake_user = SimpleNamespace(id=member_id, email="member@example.com", created_at=None)
    fake_client = SimpleNamespace(auth=SimpleNamespace(admin=SimpleNamespace(
        list_users=lambda: SimpleNamespace(users=[fake_user])
    )))
    monkeypatch.setattr(web_app, "require_admin", lambda authorization=None: {})
    monkeypatch.setattr(web_app, "_get_supabase_admin_client", lambda: fake_client)
    with membership_db() as db:
        db.add(Profile(id=member_id, is_admin=False, is_active=False))
    member = web_app.list_admin_members("Bearer admin")["members"][0]
    assert set(member) == {"user_id", "email", "created_at", "is_admin", "is_active", "kakao_connected", "morning_report_enabled"}


def test_home_uses_simple_signup_and_admin_controls(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "public-test-key")
    html = web_app.home().body.decode("utf-8")
    assert 'id="signup-form"' in html
    assert 'id="invite-code"' not in html
    assert 'id="admin-signup-enabled"' in html
    assert '"/api/admin/signup-status"' in html
    assert '"/api/admin/members/"' in html
    assert "/api/admin/invites" not in html
    assert "/api/admin/email-diagnostic" not in html
