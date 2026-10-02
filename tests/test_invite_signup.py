from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import web.app as web_app


def test_invite_code_rejected_when_not_configured(monkeypatch):
    monkeypatch.delenv("SIGNUP_INVITE_CODES", raising=False)
    assert web_app._valid_signup_invite_code("family-code") is False


def test_invite_code_accepts_only_configured_values(monkeypatch):
    monkeypatch.setenv(
        "SIGNUP_INVITE_CODES",
        "family-one, family-two",
    )

    assert web_app._valid_signup_invite_code("family-one") is True
    assert web_app._valid_signup_invite_code("family-two") is True
    assert web_app._valid_signup_invite_code("wrong-code") is False


def test_signup_rejects_invalid_invite_before_supabase(monkeypatch):
    monkeypatch.setenv("SIGNUP_INVITE_CODES", "correct-code")

    request = web_app.SignupRequest(
        email="person@example.com",
        password="password123",
        invite_code="wrong-code",
    )

    with pytest.raises(HTTPException) as exc_info:
        web_app.signup_with_invite(request)

    assert exc_info.value.status_code == 403


def test_signup_returns_session_tokens_for_valid_invite(monkeypatch):
    monkeypatch.setenv("SIGNUP_INVITE_CODES", "correct-code")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "public-anon-key")

    fake_response = SimpleNamespace(
        user=SimpleNamespace(
            email="person@example.com",
        ),
        session=SimpleNamespace(
            access_token="access-token",
            refresh_token="refresh-token",
        ),
    )

    fake_client = SimpleNamespace(
        auth=SimpleNamespace(
            sign_up=lambda payload: fake_response,
        )
    )

    monkeypatch.setattr(
        web_app,
        "create_client",
        lambda url, key: fake_client,
    )

    result = web_app.signup_with_invite(
        web_app.SignupRequest(
            email="person@example.com",
            password="password123",
            invite_code="correct-code",
        )
    )

    assert result["created"] is True
    assert result["email_confirmation_required"] is False
    assert result["access_token"] == "access-token"
    assert result["refresh_token"] == "refresh-token"


def test_signup_ui_is_invite_only(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "public-anon-key")

    response = web_app.home()
    html = response.body.decode("utf-8")

    assert 'id="signup-form"' in html
    assert 'id="invite-code"' in html
    assert '"/api/auth/signup"' in html
