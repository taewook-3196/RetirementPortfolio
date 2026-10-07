"""Kakao per-user credential isolation tests."""

from types import SimpleNamespace
import urllib.error

import services.kakao_service as kakao_module
from core.config import AppConfig, MorningReportConfig
from services.kakao_service import KakaoService


class FakeRepo:
    def __init__(self, credential):
        self.credential = credential
    def get_kakao_credential(self):
        return self.credential


def test_user_without_credential_never_inherits_shared_tokens(monkeypatch):
    monkeypatch.setenv("KAKAO_REST_API_KEY", "rest-key")
    shared = AppConfig(
        morning_report=MorningReportConfig(
            kakao_access_token="legacy-access",
            kakao_refresh_token="legacy-refresh",
        )
    )
    service = KakaoService.for_user(shared, FakeRepo(None))

    assert service.morning_cfg.kakao_access_token == ""
    assert service.morning_cfg.kakao_refresh_token == ""
    assert shared.morning_report.kakao_access_token == "legacy-access"


def test_two_users_do_not_share_tokens(monkeypatch):
    monkeypatch.setenv("KAKAO_REST_API_KEY", "rest-key")
    monkeypatch.setattr(kakao_module, "decrypt_secret", lambda value: "plain-" + value)
    shared = AppConfig(morning_report=MorningReportConfig())

    first = SimpleNamespace(
        access_token_encrypted="a1",
        refresh_token_encrypted="r1",
    )
    second = SimpleNamespace(
        access_token_encrypted="a2",
        refresh_token_encrypted="r2",
    )

    one = KakaoService.for_user(shared, FakeRepo(first))
    two = KakaoService.for_user(shared, FakeRepo(second))

    assert one.morning_cfg.kakao_access_token == "plain-a1"
    assert two.morning_cfg.kakao_access_token == "plain-a2"
    assert shared.morning_report.kakao_access_token == ""


class _AlwaysUnauthorized:
    def __enter__(self):
        raise urllib.error.HTTPError(
            "https://kapi.kakao.com",
            401,
            "Unauthorized",
            {},
            None,
        )

    def __exit__(self, exc_type, exc, tb):
        return False


def test_send_retries_token_refresh_only_once(monkeypatch):
    config = AppConfig(
        morning_report=MorningReportConfig(
            kakao_rest_api_key="rest-key",
            kakao_access_token="expired-access",
            kakao_refresh_token="refresh-token",
        )
    )
    service = KakaoService(config)
    refresh_calls = []

    def fake_refresh():
        refresh_calls.append(True)
        service.morning_cfg.kakao_access_token = "new-access"
        return True, "ok"

    monkeypatch.setattr(service, "refresh_access_token", fake_refresh)
    monkeypatch.setattr(
        kakao_module.urllib.request,
        "urlopen",
        lambda *args, **kwargs: _AlwaysUnauthorized(),
    )

    ok, message = service.send_memo_text_button(
        "test",
        "https://example.com/report",
    )

    assert ok is False
    assert len(refresh_calls) == 1
    assert "HTTP 401" in message
