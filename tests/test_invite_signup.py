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


def test_admin_invite_api_requires_admin(monkeypatch):
    monkeypatch.setattr(
        web_app,
        "require_admin",
        lambda authorization=None: (_ for _ in ()).throw(
            HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
        ),
    )
    with pytest.raises(HTTPException) as exc_info:
        web_app.create_admin_invite(
            web_app.AdminInviteCreateRequest(email="person@example.com"),
            "Bearer member",
        )
    assert exc_info.value.status_code == 403


def test_admin_creates_invite_without_storing_plaintext(monkeypatch, invite_db):
    monkeypatch.setattr(
        web_app,
        "require_admin",
        lambda authorization=None: {
            "user_id": str(uuid4()),
            "email": "admin@example.com",
        },
    )
    result = web_app.create_admin_invite(
        web_app.AdminInviteCreateRequest(
            email="Person@Example.com",
            label="Family",
            days=3,
        ),
        "Bearer admin",
    )
    assert result["email"] == "person@example.com"
    assert result["invite_code"]
    assert "비밀번호" in result["privacy_notice"]

    with invite_db() as session:
        row = session.query(InviteCode).one()
        assert row.code_hash == web_app._invite_code_hash(result["invite_code"])
        assert row.code_hash != result["invite_code"]
        assert row.intended_email == "person@example.com"


def test_admin_can_cancel_unused_invite(monkeypatch, invite_db):
    monkeypatch.setattr(web_app, "require_admin", lambda authorization=None: {})
    _insert_invite(invite_db, "cancel-me")
    with invite_db() as session:
        invite_id = session.query(InviteCode).one().id

    result = web_app.cancel_admin_invite(invite_id, "Bearer admin")
    assert result["cancelled"] is True
    with invite_db() as session:
        assert session.query(InviteCode).count() == 0


def test_admin_member_list_requires_admin(monkeypatch):
    monkeypatch.setattr(
        web_app,
        "require_admin",
        lambda authorization=None: (_ for _ in ()).throw(
            HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
        ),
    )
    with pytest.raises(HTTPException) as exc_info:
        web_app.list_admin_members("member-session")
    assert exc_info.value.status_code == 403


def test_admin_member_response_has_only_operational_fields(monkeypatch, invite_db):
    class FakeUser:
        id = uuid4()
        email = "member@example.com"
        created_at = None

    class FakeAdminAuth:
        def list_users(self):
            return type("UsersResponse", (), {"users": [FakeUser()]})()

    class FakeClient:
        auth = type("Auth", (), {"admin": FakeAdminAuth()})()

    monkeypatch.setattr(web_app, "require_admin", lambda authorization=None: {})
    monkeypatch.setattr(web_app, "_get_supabase_admin_client", lambda: FakeClient())

    with invite_db() as session:
        web_app.Profile.__table__.create(session.get_bind(), checkfirst=True)
        web_app.KakaoCredential.__table__.create(session.get_bind(), checkfirst=True)
        web_app.UserSetting.__table__.create(session.get_bind(), checkfirst=True)

    result = web_app.list_admin_members("admin-session")
    member = result["members"][0]
    assert set(member) == {
        "user_id", "email", "created_at", "is_admin",
        "kakao_connected", "morning_report_enabled",
    }
    assert "보유종목" in result["privacy_scope"]


def test_home_contains_admin_panel_without_portfolio_admin_controls(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "public-test-key")
    response = web_app.home()
    html = response.body.decode("utf-8")
    assert 'id="admin-section"' in html
    assert 'id="admin-invite-form"' in html
    assert 'id="admin-members"' in html
    assert 'id="admin-invites"' in html
    assert '"/api/admin/members"' in html
    assert '"/api/admin/invites"' in html
    assert "증권사 비밀번호" in html
    assert "API 비밀키" in html
    assert "투자 데이터는 이 화면에서 열람할 수 없습니다" in html


def test_admin_invite_returns_fragment_link(monkeypatch, invite_db):
    monkeypatch.setattr(web_app, "require_admin", lambda authorization=None: {})
    result = web_app.create_admin_invite(
        web_app.AdminInviteCreateRequest(email="invitee@example.com"),
        "admin-session",
    )
    assert result["invite_url"].startswith(
        "https://retirementportfolio.onrender.com/#invite="
    )
    assert "?invite=" not in result["invite_url"]


def test_home_prefills_fragment_invite_without_query_secret(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "public-test-key")
    html = web_app.home().body.decode("utf-8")
    assert 'hash.startsWith("#invite=")' in html
    assert "history.replaceState" in html
    assert "?invite=" not in html


def test_home_contains_admin_email_diagnostic_button(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "public-test-key")
    html = web_app.home().body.decode("utf-8")
    assert 'id="admin-email-test-button"' in html
    assert '"/api/admin/email-diagnostic"' in html
    assert "Resend가 테스트 메일을 접수했습니다." in html


def test_admin_email_diagnostic_uses_existing_token_storage(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "public-test-key")
    html = web_app.home().body.decode("utf-8")
    marker = 'document.getElementById("admin-email-test-button").addEventListener'
    block = html[html.index(marker):html.index('adminInviteForm.addEventListener', html.index(marker))]
    assert 'localStorage.getItem("access_token")' in block
    assert 'sessionStorage.getItem("access_token")' in block
    assert "getStoredSession" not in block


def test_admin_email_diagnostic_listener_is_attached_in_late_app_setup(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "public-test-key")
    html = web_app.home().body.decode("utf-8")
    assert "async function runAdminEmailDiagnostic" in html
    assert 'const adminEmailTestButton = document.getElementById("admin-email-test-button")' in html
    assert html.index("async function runAdminEmailDiagnostic") < html.index("function saveAuthTokens")
