"""공개 Web/Morning Report URL 설정의 우선순위와 보안을 검증합니다."""

import json
import urllib.parse
from unittest.mock import patch

from core.config import (
    DEFAULT_REPORT_URL,
    DEFAULT_WEB_APP_URL,
    get_default_config,
    get_report_url,
    get_web_app_url,
    validate_public_url,
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


def test_default_web_url(monkeypatch):
    monkeypatch.delenv("RETIREMENT_PORTFOLIO_WEB_URL", raising=False)
    assert get_web_app_url() == DEFAULT_WEB_APP_URL


def test_web_url_override(monkeypatch):
    monkeypatch.setenv("RETIREMENT_PORTFOLIO_WEB_URL", "https://web.example/app")
    assert get_web_app_url() == "https://web.example/app/"


def test_invalid_web_url_scheme_falls_back(monkeypatch):
    monkeypatch.setenv("RETIREMENT_PORTFOLIO_WEB_URL", "javascript:alert(1)")
    assert get_web_app_url() == DEFAULT_WEB_APP_URL


def test_default_report_url(monkeypatch):
    _clear_report_environment(monkeypatch)
    assert get_report_url() == DEFAULT_REPORT_URL


def test_report_url_override(monkeypatch):
    _clear_report_environment(monkeypatch)
    monkeypatch.setenv("RETIREMENT_PORTFOLIO_REPORT_URL", "https://reports.example/latest")
    assert get_report_url() == "https://reports.example/latest/"


def test_report_url_override_preserves_report_view_query(monkeypatch):
    _clear_report_environment(monkeypatch)
    monkeypatch.setenv(
        "RETIREMENT_PORTFOLIO_REPORT_URL",
        "https://retirementportfolio.onrender.com/?view=report",
    )
    assert get_report_url() == "https://retirementportfolio.onrender.com/?view=report"


def test_invalid_report_url_scheme_falls_back(monkeypatch):
    _clear_report_environment(monkeypatch)
    monkeypatch.setenv("RETIREMENT_PORTFOLIO_REPORT_URL", "data:text/html,unsafe")
    assert get_report_url() == DEFAULT_REPORT_URL


def test_legacy_github_pages_base_url_is_ignored(monkeypatch):
    _clear_report_environment(monkeypatch)
    monkeypatch.setenv("GITHUB_PAGES_BASE_URL", "https://legacy.example/report")
    assert get_report_url() == DEFAULT_REPORT_URL


def test_github_repository_does_not_build_pages_url(monkeypatch):
    _clear_report_environment(monkeypatch)
    monkeypatch.setenv("GITHUB_REPOSITORY", "ExampleOwner/ExampleRepo")
    assert get_report_url() == DEFAULT_REPORT_URL


def test_kakao_report_url_uses_shared_fallback(monkeypatch):
    _clear_report_environment(monkeypatch)
    monkeypatch.setenv("RETIREMENT_PORTFOLIO_REPORT_URL", "https://reports.example/")
    config = get_default_config()
    config.morning_report.kakao_access_token = "test-token"

    response = type("Response", (), {
        "status": 200,
        "read": lambda self: b'{"result_code": 0}',
        "__enter__": lambda self: self,
        "__exit__": lambda self, *args: None,
    })()
    with patch("urllib.request.urlopen", return_value=response) as urlopen:
        ok, _ = KakaoService(config).send_morning_report("summary", "javascript:bad")

    assert ok
    request = urlopen.call_args.args[0]
    form = urllib.parse.parse_qs(request.data.decode("utf-8"))
    template = json.loads(form["template_object"][0])
    assert template["link"]["web_url"] == "https://reports.example/"


def test_web_html_does_not_expose_server_secrets(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "public-anon-key")
    secrets = {
        "DATABASE_URL": "postgresql://server-secret",
        "KRX_API_KEY": "server-krx-secret",
        "GEMINI_API_KEY": "server-gemini-secret",
        "KAKAO_ACCESS_TOKEN": "server-kakao-secret",
    }
    for name, value in secrets.items():
        monkeypatch.setenv(name, value)

    html = home().body.decode("utf-8")
    for value in secrets.values():
        assert value not in html


def test_validate_public_url_preserves_report_query():
    url = "https://retirementportfolio.onrender.com/?view=report"
    assert validate_public_url(url, DEFAULT_REPORT_URL) == url
