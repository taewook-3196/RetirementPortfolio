"""공개 URL 중앙 설정과 브라우저 secret 격리 회귀 테스트."""

import json
import urllib.parse

from core.config import (
    AppConfig,
    DEFAULT_REPORT_URL,
    DEFAULT_WEB_APP_URL,
    MorningReportConfig,
    get_report_url,
    get_web_app_url,
)
from services.kakao_service import KakaoService
from web.app import home


def _clear_report_environment(monkeypatch):
    for name in (
        "RETIREMENT_PORTFOLIO_REPORT_URL",
        "GITHUB_PAGES_BASE_URL",
        "GITHUB_REPOSITORY",
    ):
        monkeypatch.delenv(name, raising=False)


def test_public_url_defaults(monkeypatch):
    monkeypatch.delenv("RETIREMENT_PORTFOLIO_WEB_URL", raising=False)
    _clear_report_environment(monkeypatch)

    assert get_web_app_url() == DEFAULT_WEB_APP_URL
    assert get_report_url() == DEFAULT_REPORT_URL


def test_public_url_overrides_and_invalid_scheme_fallback(monkeypatch):
    monkeypatch.setenv("RETIREMENT_PORTFOLIO_WEB_URL", "https://web.example/app")
    monkeypatch.setenv("RETIREMENT_PORTFOLIO_REPORT_URL", "https://pages.example/report")
    assert get_web_app_url() == "https://web.example/app/"
    assert get_report_url() == "https://pages.example/report/"

    monkeypatch.setenv("RETIREMENT_PORTFOLIO_WEB_URL", "javascript:alert(1)")
    monkeypatch.setenv("RETIREMENT_PORTFOLIO_REPORT_URL", "data:text/html,bad")
    assert get_web_app_url() == DEFAULT_WEB_APP_URL
    assert get_report_url() == DEFAULT_REPORT_URL


def test_report_url_keeps_legacy_environment_compatibility(monkeypatch):
    _clear_report_environment(monkeypatch)
    monkeypatch.setenv("GITHUB_PAGES_BASE_URL", "https://legacy.example/pages")
    assert get_report_url() == "https://legacy.example/pages/"


def test_kakao_invalid_link_uses_central_report_url(monkeypatch):
    monkeypatch.setenv("RETIREMENT_PORTFOLIO_REPORT_URL", "https://pages.example/report")
    captured = {}

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"result_code": 0}'

    def fake_urlopen(request, **_kwargs):
        form = urllib.parse.parse_qs(request.data.decode("utf-8"))
        captured.update(json.loads(form["template_object"][0]))
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    config = AppConfig(
        morning_report=MorningReportConfig(kakao_access_token="test-token")
    )

    ok, _ = KakaoService(config).send_morning_report("요약", "javascript:bad")

    assert ok is True
    assert captured["link"]["web_url"] == "https://pages.example/report/"


def test_web_html_exposes_only_supabase_public_configuration(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://public.example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "public-anon-key")
    server_secrets = {
        "DATABASE_URL": "postgresql://server-secret",
        "GEMINI_API_KEY": "gemini-server-secret",
        "KAKAO_ACCESS_TOKEN": "kakao-server-secret",
        "KRX_API_KEY": "krx-server-secret",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role-secret",
        "GITHUB_TOKEN": "github-server-secret",
    }
    for name, value in server_secrets.items():
        monkeypatch.setenv(name, value)

    response = home()
    content = response.body.decode("utf-8")

    assert "https://public.example.supabase.co" in content
    assert "public-anon-key" in content
    for value in server_secrets.values():
        assert value not in content
