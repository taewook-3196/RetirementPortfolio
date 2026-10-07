from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import web.app as web_app
from database.models import AppSetting, DeletedMember, KakaoCredential, Profile, UserSetting


@pytest.fixture
def membership_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Profile.__table__.create(engine)
    AppSetting.__table__.create(engine)
    DeletedMember.__table__.create(engine)
    KakaoCredential.__table__.create(engine)
    UserSetting.__table__.create(engine)
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


def test_home_allows_kakao_disconnect_when_reconnect_is_required(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    html = web_app.home().body.decode("utf-8")
    assert (
        'kakaoDisconnectButton.style.display = data.connected || data.needs_reconnect ? "block" : "none";'
        in html
    )
    assert 'kakaoTestButton.style.display = data.connected ? "block" : "none";' in html


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
    assert '"/api/bootstrap"' in html
    assert "await showAuthenticatedApp(data.access_token)" in html
    assert '로그인 계정 삭제' in html
    assert '투자 데이터와 기존 리포트는 서버에 보존되지만, 새 계정을 만들어도 자동으로 연결되지는 않습니다.' in html


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
        tombstone = db.query(DeletedMember).filter(DeletedMember.user_id == member_id).one()
        assert tombstone.deleted_by == admin_id
        assert tombstone.deleted_at is not None


def test_failed_auth_deletion_does_not_create_tombstone(monkeypatch, membership_db):
    admin_id, member_id = uuid4(), uuid4()
    with membership_db() as db:
        db.add(Profile(id=member_id, is_admin=False, is_active=True))
    monkeypatch.setattr(
        web_app,
        "require_admin",
        lambda authorization=None: {"user_id": str(admin_id)},
    )

    def fail_delete(user_id):
        raise RuntimeError("auth unavailable")

    monkeypatch.setattr(
        web_app,
        "_get_supabase_admin_client",
        lambda: SimpleNamespace(
            auth=SimpleNamespace(admin=SimpleNamespace(delete_user=fail_delete))
        ),
    )

    with pytest.raises(HTTPException) as exc:
        web_app.delete_member(member_id, "Bearer admin")

    assert exc.value.status_code == 502
    with membership_db() as db:
        profile = db.query(Profile).filter(Profile.id == member_id).one()
        assert profile.is_active is False
        assert db.query(DeletedMember).filter(DeletedMember.user_id == member_id).one_or_none() is None


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



def test_kakao_callback_rejects_suspended_member_before_token_exchange(
    monkeypatch,
    membership_db,
):
    user_id = uuid4()
    with membership_db() as db:
        db.add(Profile(id=user_id, is_admin=False, is_active=False))

    state = web_app._kakao_state_serializer().dumps({
        "user_id": str(user_id),
        "purpose": "kakao-connect",
    })
    token_exchange_called = []
    monkeypatch.setattr(
        web_app.urllib.request,
        "urlopen",
        lambda *args, **kwargs: token_exchange_called.append(True),
    )

    with pytest.raises(HTTPException) as exc:
        web_app.kakao_callback(code="one-time-code", state=state)

    assert exc.value.status_code == 403
    assert token_exchange_called == []


def test_kakao_callback_rejects_deleted_member_before_token_exchange(
    monkeypatch,
    membership_db,
):
    user_id = uuid4()
    state = web_app._kakao_state_serializer().dumps({
        "user_id": str(user_id),
        "purpose": "kakao-connect",
    })
    token_exchange_called = []
    monkeypatch.setattr(
        web_app.urllib.request,
        "urlopen",
        lambda *args, **kwargs: token_exchange_called.append(True),
    )

    with pytest.raises(HTTPException) as exc:
        web_app.kakao_callback(code="one-time-code", state=state)

    assert exc.value.status_code == 403
    assert token_exchange_called == []



def test_admin_cannot_suspend_another_admin(monkeypatch, membership_db):
    admin_id, other_admin_id = uuid4(), uuid4()
    with membership_db() as db:
        db.add(Profile(id=other_admin_id, is_admin=True, is_active=True))
    monkeypatch.setattr(
        web_app,
        "require_admin",
        lambda authorization=None: {"user_id": str(admin_id)},
    )

    with pytest.raises(HTTPException) as exc:
        web_app.set_member_access(
            other_admin_id,
            web_app.MemberAccessRequest(active=False),
            "Bearer admin",
        )

    assert exc.value.status_code == 400
    with membership_db() as db:
        profile = db.query(Profile).filter(Profile.id == other_admin_id).one()
        assert profile.is_active is True


def test_admin_cannot_delete_unknown_member(monkeypatch, membership_db):
    admin_id, unknown_id = uuid4(), uuid4()
    delete_calls = []
    monkeypatch.setattr(
        web_app,
        "require_admin",
        lambda authorization=None: {"user_id": str(admin_id)},
    )
    monkeypatch.setattr(
        web_app,
        "_get_supabase_admin_client",
        lambda: SimpleNamespace(
            auth=SimpleNamespace(
                admin=SimpleNamespace(
                    delete_user=lambda user_id: delete_calls.append(user_id)
                )
            )
        ),
    )

    with pytest.raises(HTTPException) as exc:
        web_app.delete_member(unknown_id, "Bearer admin")

    assert exc.value.status_code == 404
    assert delete_calls == []


def test_signup_remains_successful_when_auto_login_fails(monkeypatch, membership_db):
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
    public_client = SimpleNamespace(
        auth=SimpleNamespace(
            sign_in_with_password=lambda payload: (_ for _ in ()).throw(
                RuntimeError("temporary login failure")
            )
        )
    )
    monkeypatch.setattr(
        web_app,
        "create_client",
        lambda url, key: admin_client if key == "service" else public_client,
    )

    result = web_app.signup(
        web_app.SignupRequest(
            email="person@example.com",
            password="password123",
        )
    )

    assert result["created"] is True
    assert result["login_required"] is True
    assert result["access_token"] is None
    assert result["refresh_token"] is None
    assert deleted_auth_users == []
    with membership_db() as db:
        profile = db.query(Profile).filter(Profile.id == user_id).one_or_none()
        assert profile is not None
        assert profile.is_active is True



def test_member_delete_auth_failure_leaves_profile_suspended(monkeypatch, membership_db):
    admin_id, member_id = uuid4(), uuid4()
    with membership_db() as db:
        db.add(Profile(id=member_id, is_admin=False, is_active=True))

    monkeypatch.setattr(
        web_app,
        "require_admin",
        lambda authorization=None: {"user_id": str(admin_id)},
    )

    def fail_delete(user_id):
        raise RuntimeError("auth unavailable")

    admin_api = SimpleNamespace(delete_user=fail_delete)
    monkeypatch.setattr(
        web_app,
        "_get_supabase_admin_client",
        lambda: SimpleNamespace(auth=SimpleNamespace(admin=admin_api)),
    )

    with pytest.raises(HTTPException) as exc:
        web_app.delete_member(member_id, "Bearer admin")

    assert exc.value.status_code == 502
    with membership_db() as db:
        profile = db.query(Profile).filter(Profile.id == member_id).one()
        assert profile.is_active is False



def test_bootstrap_initializes_only_authenticated_active_user(monkeypatch):
    user_id = uuid4()
    monkeypatch.setattr(
        web_app,
        "get_verified_user_id",
        lambda authorization=None: str(user_id),
    )
    calls = []

    class FakeRepository:
        def __init__(self, user_id):
            calls.append(("repository", user_id))

        def ensure_user_initialized(self):
            calls.append(("initialize", str(user_id)))
            return {"settings_created": True, "profile_created": False}

    monkeypatch.setattr(web_app, "Repository", FakeRepository)

    result = web_app.bootstrap_current_user("Bearer valid-token")

    assert result == {
        "initialized": True,
        "settings_created": True,
        "profile_created": False,
    }
    assert calls == [
        ("repository", str(user_id)),
        ("initialize", str(user_id)),
    ]


def test_bootstrap_does_not_initialize_when_authentication_fails(monkeypatch):
    repository_calls = []

    def reject_user(authorization=None):
        raise HTTPException(status_code=403, detail="현재 이용 가능한 회원 계정이 아닙니다.")

    monkeypatch.setattr(web_app, "get_verified_user_id", reject_user)
    monkeypatch.setattr(
        web_app,
        "Repository",
        lambda user_id: repository_calls.append(user_id),
    )

    with pytest.raises(HTTPException) as exc:
        web_app.bootstrap_current_user("Bearer suspended-token")

    assert exc.value.status_code == 403
    assert repository_calls == []



def test_kakao_callback_rejects_token_without_talk_message_scope(monkeypatch, membership_db):
    user_id = uuid4()
    with membership_db() as db:
        db.add(Profile(id=user_id, is_admin=False, is_active=True))

    monkeypatch.setenv("KAKAO_REST_API_KEY", "rest-key")
    monkeypatch.setenv("OAUTH_TOKEN_ENCRYPTION_KEY", "test-secret")
    monkeypatch.setenv("RETIREMENT_PORTFOLIO_WEB_URL", "https://example.com")

    state = web_app._kakao_state_serializer().dumps({
        "user_id": str(user_id),
        "purpose": "kakao-connect",
    })

    class FakeResponse:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return b'{"access_token":"access","refresh_token":"refresh","scope":""}'

    monkeypatch.setattr(web_app.urllib.request, "urlopen", lambda *args, **kwargs: FakeResponse())

    with pytest.raises(HTTPException) as exc:
        web_app.kakao_callback(code="one-time-code", state=state)

    assert exc.value.status_code == 403
    assert "talk_message" in exc.value.detail
    assert "카카오톡 메시지 전송" in exc.value.detail



def test_kakao_status_requires_talk_message_scope(monkeypatch):
    user_id = uuid4()
    monkeypatch.setattr(
        web_app,
        "get_verified_user_id",
        lambda authorization=None: str(user_id),
    )

    class Credential:
        scopes = ""

    class FakeRepository:
        def __init__(self, user_id):
            self.user_id = user_id

        def get_kakao_credential(self):
            return Credential()

    monkeypatch.setattr(web_app, "Repository", FakeRepository)

    result = web_app.kakao_status("Bearer valid-token")

    assert result == {"connected": False, "needs_reconnect": True}


def test_kakao_status_accepts_talk_message_scope(monkeypatch):
    user_id = uuid4()
    monkeypatch.setattr(
        web_app,
        "get_verified_user_id",
        lambda authorization=None: str(user_id),
    )

    class Credential:
        scopes = "profile_nickname talk_message"

    class FakeRepository:
        def __init__(self, user_id):
            self.user_id = user_id

        def get_kakao_credential(self):
            return Credential()

    monkeypatch.setattr(web_app, "Repository", FakeRepository)

    result = web_app.kakao_status("Bearer valid-token")

    assert result == {"connected": True, "needs_reconnect": False}


def test_non_admin_is_rejected_by_admin_guard(monkeypatch, membership_db):
    member_id = uuid4()
    with membership_db() as db:
        db.add(Profile(id=member_id, is_admin=False, is_active=True))
    monkeypatch.setattr(
        web_app,
        "get_current_user",
        lambda authorization=None: {
            "authenticated": True,
            "user_id": str(member_id),
            "email": "member@example.com",
        },
    )

    with pytest.raises(HTTPException) as exc:
        web_app.require_admin("Bearer member")

    assert exc.value.status_code == 403


def test_non_admin_cannot_reach_admin_member_operations(monkeypatch, membership_db):
    member_id, target_id = uuid4(), uuid4()
    with membership_db() as db:
        db.add(Profile(id=member_id, is_admin=False, is_active=True))
        db.add(Profile(id=target_id, is_admin=False, is_active=True))
    monkeypatch.setattr(
        web_app,
        "get_current_user",
        lambda authorization=None: {
            "authenticated": True,
            "user_id": str(member_id),
            "email": "member@example.com",
        },
    )

    operations = [
        lambda: web_app.set_signup_status(
            web_app.SignupControlRequest(enabled=True), "Bearer member"
        ),
        lambda: web_app.list_admin_members("Bearer member"),
        lambda: web_app.set_member_access(
            target_id, web_app.MemberAccessRequest(active=False), "Bearer member"
        ),
        lambda: web_app.delete_member(target_id, "Bearer member"),
    ]
    for operation in operations:
        with pytest.raises(HTTPException) as exc:
            operation()
        assert exc.value.status_code == 403

    with membership_db() as db:
        assert db.query(AppSetting).filter(AppSetting.key == web_app.SIGNUP_ENABLED_KEY).one_or_none() is None
        assert db.query(Profile).filter(Profile.id == target_id).one().is_active is True


def test_admin_member_list_exposes_only_operational_fields(monkeypatch, membership_db):
    admin_id, member_id = uuid4(), uuid4()
    with membership_db() as db:
        db.add(Profile(id=admin_id, is_admin=True, is_active=True))
        db.add(Profile(id=member_id, is_admin=False, is_active=True))
    monkeypatch.setattr(
        web_app,
        "require_admin",
        lambda authorization=None: {"user_id": str(admin_id)},
    )
    auth_user = SimpleNamespace(id=member_id, email="member@example.com", created_at=None)
    monkeypatch.setattr(
        web_app,
        "_get_supabase_admin_client",
        lambda: SimpleNamespace(
            auth=SimpleNamespace(
                admin=SimpleNamespace(list_users=lambda: SimpleNamespace(users=[auth_user]))
            )
        ),
    )

    result = web_app.list_admin_members("Bearer admin")
    member = result["members"][0]
    assert set(member) == {
        "user_id", "email", "created_at", "is_admin", "is_active",
        "kakao_connected", "morning_report_enabled",
    }
    private_fields = {
        "holdings", "transactions", "cash_balance", "portfolio_value",
        "investment_profile", "morning_report", "account_number",
    }
    assert private_fields.isdisjoint(member)


def test_deleted_member_list_is_admin_only_and_privacy_safe(monkeypatch, membership_db):
    admin_id, deleted_id = uuid4(), uuid4()
    with membership_db() as db:
        db.add(DeletedMember(user_id=deleted_id, deleted_by=admin_id))

    monkeypatch.setattr(
        web_app,
        "require_admin",
        lambda authorization=None: {"user_id": str(admin_id)},
    )
    monkeypatch.setattr(web_app, "_has_retained_member_data", lambda user_id: True)

    result = web_app.list_deleted_members("Bearer admin")
    assert len(result["deleted_members"]) == 1
    item = result["deleted_members"][0]
    assert set(item) == {"user_id", "deleted_at", "has_retained_data"}
    assert item["user_id"] == str(deleted_id)
    assert item["has_retained_data"] is True
    assert "email" not in item
    assert "holdings" not in item
    assert "transactions" not in item
    assert "portfolio_value" not in item


def test_non_admin_cannot_list_deleted_members(monkeypatch, membership_db):
    member_id = uuid4()
    with membership_db() as db:
        db.add(Profile(id=member_id, is_admin=False, is_active=True))
    monkeypatch.setattr(
        web_app,
        "get_current_user",
        lambda authorization=None: {
            "authenticated": True,
            "user_id": str(member_id),
            "email": "member@example.com",
        },
    )

    with pytest.raises(HTTPException) as exc:
        web_app.list_deleted_members("Bearer member")
    assert exc.value.status_code == 403


def test_purge_requires_exact_deleted_member_confirmation(monkeypatch, membership_db):
    admin_id, deleted_id = uuid4(), uuid4()
    monkeypatch.setattr(web_app, "require_admin", lambda authorization=None: {"user_id": str(admin_id)})
    with membership_db() as db:
        db.add(DeletedMember(user_id=deleted_id, deleted_by=admin_id))

    with pytest.raises(HTTPException) as exc:
        web_app.purge_deleted_member_data(
            deleted_id,
            web_app.DeletedMemberPurgeRequest(confirm_user_id=uuid4()),
            "Bearer admin",
        )
    assert exc.value.status_code == 400
    with membership_db() as db:
        assert db.query(DeletedMember).filter(DeletedMember.user_id == deleted_id).one_or_none() is not None


def test_purge_rejects_user_without_deleted_member_tombstone(monkeypatch, membership_db):
    admin_id, member_id = uuid4(), uuid4()
    monkeypatch.setattr(web_app, "require_admin", lambda authorization=None: {"user_id": str(admin_id)})
    with pytest.raises(HTTPException) as exc:
        web_app.purge_deleted_member_data(
            member_id,
            web_app.DeletedMemberPurgeRequest(confirm_user_id=member_id),
            "Bearer admin",
        )
    assert exc.value.status_code == 404


def test_purge_rejects_deleted_id_if_profile_exists(monkeypatch, membership_db):
    admin_id, member_id = uuid4(), uuid4()
    monkeypatch.setattr(web_app, "require_admin", lambda authorization=None: {"user_id": str(admin_id)})
    with membership_db() as db:
        db.add(Profile(id=member_id, is_admin=False, is_active=False))
        db.add(DeletedMember(user_id=member_id, deleted_by=admin_id))
    with pytest.raises(HTTPException) as exc:
        web_app.purge_deleted_member_data(
            member_id,
            web_app.DeletedMemberPurgeRequest(confirm_user_id=member_id),
            "Bearer admin",
        )
    assert exc.value.status_code == 409


def test_non_admin_cannot_purge_deleted_member(monkeypatch, membership_db):
    member_id, deleted_id = uuid4(), uuid4()
    with membership_db() as db:
        db.add(Profile(id=member_id, is_admin=False, is_active=True))
        db.add(DeletedMember(user_id=deleted_id, deleted_by=member_id))
    monkeypatch.setattr(
        web_app,
        "get_current_user",
        lambda authorization=None: {"authenticated": True, "user_id": str(member_id), "email": "member@example.com"},
    )
    with pytest.raises(HTTPException) as exc:
        web_app.purge_deleted_member_data(
            deleted_id,
            web_app.DeletedMemberPurgeRequest(confirm_user_id=deleted_id),
            "Bearer member",
        )
    assert exc.value.status_code == 403
