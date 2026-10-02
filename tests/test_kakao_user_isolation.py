"""Kakao per-user credential isolation tests."""

from types import SimpleNamespace

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
