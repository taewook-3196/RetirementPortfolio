from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import web.app as web_app
from database.models import AppSetting, Profile


@pytest.fixture
def membership_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Profile.__table__.create(engine)
    AppSetting.__table__.create(engine)
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


def test_signup_defaults_to_disabled_when_setting_missing(membership_db):
    assert web_app.get_signup_status() == {"signup_enabled": False}


def test_admin_can_enable_and_disable_signup(monkeypatch, membership_db):
    monkeypatch.setattr(web_app, "require_admin", lambda authorization=None: {"user_id": str(uuid4())})
    enabled = web_app.set_signup_status(web_app.SignupControlRequest(enabled=True), "Bearer admin")
    assert enabled == {"signup_enabled": True}
    assert web_app.get_signup_status() == {"signup_enabled": True}

    disabled = web_app.set_signup_status(web_app.SignupControlRequest(enabled=False), "Bearer admin")
    assert disabled == {"signup_enabled": False}
    assert web_app.get_signup_status() == {"signup_enabled": False}


def test_signup_is_rejected_while_disabled(monkeypatch):
    monkeypatch.setattr(web_app, "_signup_enabled", lambda: False)
    with pytest.raises(HTTPException) as exc:
        web_app.signup(web_app.SignupRequest(email="person@example.com", password="password123"))
    assert exc.value.status_code == 403


def test_signup_creates_active_profile_when_enabled(monkeypatch, membership_db):
    monkeypatch.setattr(web_app, "_signup_enabled", lambda: True)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service")
    user_id = uuid4()
    created_user = SimpleNamespace(id=user_id, email="person@example.com")
    admin_client = SimpleNamespace(auth=SimpleNamespace(admin=SimpleNamespace(
        create_user=lambda payload: SimpleNamespace(user=created_user)
    )))
    public_client = SimpleNamespace(auth=SimpleNamespace(
        sign_in_with_password=lambda payload: SimpleNamespace(
            session=SimpleNamespace(access_token="access", refresh_token="refresh")
        )
    ))
    monkeypatch.setattr(
        web_app,
        "create_client",
        lambda url, key: admin_client if key == "service" else public_client,
    )

    result = web_app.signup(web_app.SignupRequest(email="Person@Example.com", password="password123"))
    assert result["created"] is True
    assert result["access_token"] == "access"
    with membership_db() as db:
        profile = db.query(Profile).filter(Profile.id == user_id).one()
        assert profile.is_active is True
        assert profile.is_admin is False


def test_admin_cannot_suspend_self(monkeypatch, membership_db):
    admin_id = uuid4()
    monkeypatch.setattr(web_app, "require_admin", lambda authorization=None: {"user_id": str(admin_id)})
    with pytest.raises(HTTPException) as exc:
        web_app.set_member_access(
            admin_id,
            web_app.MemberAccessRequest(active=False),
            "Bearer admin",
        )
    assert exc.value.status_code == 400


def test_admin_can_suspend_and_reactivate_member(monkeypatch, membership_db):
    admin_id, member_id = uuid4(), uuid4()
    with membership_db() as db:
        db.add(Profile(id=member_id, is_admin=False, is_active=True))
    monkeypatch.setattr(web_app, "require_admin", lambda authorization=None: {"user_id": str(admin_id)})

    result = web_app.set_member_access(
        member_id, web_app.MemberAccessRequest(active=False), "Bearer admin"
    )
    assert result["is_active"] is False
    with membership_db() as db:
        assert db.query(Profile).filter(Profile.id == member_id).one().is_active is False

    result = web_app.set_member_access(
        member_id, web_app.MemberAccessRequest(active=True), "Bearer admin"
    )
    assert result["is_active"] is True


def test_home_has_signup_gate_and_no_invitation_ui(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    html = web_app.home().body.decode("utf-8")
    assert 'id="admin-signup-enabled"' in html
    assert '"/api/signup-status"' in html
    assert '"/api/admin/signup-status"' in html
    assert 'invite-code' not in html
    assert 'admin-invite-form' not in html
    assert 'email-diagnostic' not in html
    assert 'body: JSON.stringify({email, password})' in html
    assert '로그인 계정 삭제' in html
    assert '투자 데이터와 기존 리포트는 복구 안전을 위해 자동 삭제하지 않습니다.' in html


def _mock_authenticated_user(monkeypatch, user_id):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    auth = SimpleNamespace(
        get_user=lambda token: SimpleNamespace(
            user=SimpleNamespace(id=user_id, email="member@example.com")
        )
    )
    monkeypatch.setattr(
        web_app,
        "create_client",
        lambda url, key: SimpleNamespace(auth=auth),
    )


def test_authenticated_user_without_profile_is_rejected(monkeypatch, membership_db):
    user_id = uuid4()
    _mock_authenticated_user(monkeypatch, user_id)

    with pytest.raises(HTTPException) as exc:
        web_app.get_current_user("Bearer still-valid-token")

    assert exc.value.status_code == 403


def test_authenticated_active_profile_is_allowed(monkeypatch, membership_db):
    user_id = uuid4()
    with membership_db() as db:
        db.add(Profile(id=user_id, is_admin=False, is_active=True))
    _mock_authenticated_user(monkeypatch, user_id)

    result = web_app.get_current_user("Bearer valid-token")

    assert result["authenticated"] is True
    assert result["user_id"] == str(user_id)


def test_admin_cannot_delete_self(monkeypatch, membership_db):
    admin_id = uuid4()
    monkeypatch.setattr(
        web_app,
        "require_admin",
        lambda authorization=None: {"user_id": str(admin_id)},
    )

    with pytest.raises(HTTPException) as exc:
        web_app.delete_member(admin_id, "Bearer admin")

    assert exc.value.status_code == 400


def test_admin_cannot_delete_another_admin(monkeypatch, membership_db):
    admin_id, other_admin_id = uuid4(), uuid4()
    with membership_db() as db:
        db.add(Profile(id=other_admin_id, is_admin=True, is_active=True))
    monkeypatch.setattr(
        web_app,
        "require_admin",
        lambda authorization=None: {"user_id": str(admin_id)},
    )

    with pytest.raises(HTTPException) as exc:
        web_app.delete_member(other_admin_id, "Bearer admin")

    assert exc.value.status_code == 400


def test_admin_deletes_member_login_but_reports_data_retained(monkeypatch, membership_db):
    admin_id, member_id = uuid4(), uuid4()
    deleted_auth_users = []
    with membership_db() as db:
        db.add(Profile(id=member_id, is_admin=False, is_active=True))
    monkeypatch.setattr(
        web_app,
        "require_admin",
        lambda authorization=None: {"user_id": str(admin_id)},
    )
    admin_api = SimpleNamespace(
        delete_user=lambda user_id: deleted_auth_users.append(user_id)
    )
    monkeypatch.setattr(
        web_app,
        "_get_supabase_admin_client",
        lambda: SimpleNamespace(auth=SimpleNamespace(admin=admin_api)),
    )

    result = web_app.delete_member(member_id, "Bearer admin")

    assert deleted_auth_users == [str(member_id)]
    assert result == {
        "deleted": True,
        "user_id": str(member_id),
        "portfolio_data_deleted": False,
    }
    with membership_db() as db:
        assert db.query(Profile).filter(Profile.id == member_id).one_or_none() is None


def test_admin_cannot_create_profile_for_unknown_member(monkeypatch, membership_db):
    admin_id, unknown_id = uuid4(), uuid4()
    monkeypatch.setattr(
        web_app,
        "require_admin",
        lambda authorization=None: {"user_id": str(admin_id)},
    )

    with pytest.raises(HTTPException) as exc:
        web_app.set_member_access(
            unknown_id,
            web_app.MemberAccessRequest(active=True),
            "Bearer admin",
        )

    assert exc.value.status_code == 404
    with membership_db() as db:
        assert db.query(Profile).filter(Profile.id == unknown_id).one_or_none() is None


def test_signup_rolls_back_auth_user_when_profile_write_fails(monkeypatch):
    monkeypatch.setattr(web_app, "_signup_enabled", lambda: True)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service")
    user_id = uuid4()
    deleted_auth_users = []
    created_user = SimpleNamespace(id=user_id, email="person@example.com")
    admin_api = SimpleNamespace(
        create_user=lambda payload: SimpleNamespace(user=created_user),
        delete_user=lambda value: deleted_auth_users.append(value),
    )
    admin_client = SimpleNamespace(auth=SimpleNamespace(admin=admin_api))
    monkeypatch.setattr(web_app, "create_client", lambda url, key: admin_client)

    @contextmanager
    def failing_session():
        raise RuntimeError("database unavailable")
        yield

    monkeypatch.setattr(web_app, "get_db_session", failing_session)

    with pytest.raises(HTTPException) as exc:
        web_app.signup(
            web_app.SignupRequest(
                email="person@example.com",
                password="password123",
            )
        )

    assert exc.value.status_code == 500
    assert deleted_auth_users == [str(user_id)]
