from contextlib import contextmanager
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import database.repository as repository_module
import web.app as web_app
from core.config import AppConfig, get_report_url
from database.models import MorningReport
from database.repository import Repository
from services.report_html_generator import ReportHtmlGenerator


@pytest.fixture
def report_session(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    MorningReport.__table__.create(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    @contextmanager
    def session_scope():
        session = factory()
        try:
            yield session
            session.commit()
        finally:
            session.close()

    monkeypatch.setattr(repository_module, "get_db_session", session_scope)
    return factory


def make_repo(user_id):
    repo = object.__new__(Repository)
    repo.user_id = user_id
    return repo


def test_report_upsert_and_owner_isolation(report_session):
    user_a, user_b = uuid4(), uuid4()
    repo_a, repo_b = make_repo(user_a), make_repo(user_b)
    repo_a.upsert_morning_report(date(2026, 10, 2), "first")
    repo_a.upsert_morning_report(date(2026, 10, 2), "replacement")

    assert repo_a.get_latest_morning_report().html_content == "replacement"
    assert repo_b.get_latest_morning_report() is None
    with report_session() as session:
        assert session.query(MorningReport).count() == 1


def test_private_report_api_requires_authentication():
    with pytest.raises(HTTPException) as exc_info:
        web_app.get_latest_morning_report(authorization=None)
    assert exc_info.value.status_code == 401


def test_private_report_api_uses_verified_owner(monkeypatch):
    captured = {}

    class FakeRepository:
        def __init__(self, user_id):
            captured["user_id"] = user_id

        def get_latest_morning_report(self):
            return type("Report", (), {"html_content": "<h1>private</h1>"})()

    monkeypatch.setattr(web_app, "get_verified_user_id", lambda token: "user-a")
    monkeypatch.setattr(web_app, "Repository", FakeRepository)
    response = web_app.get_latest_morning_report("Bearer valid")
    assert captured["user_id"] == "user-a"
    assert "private" in response.body.decode()
    assert response.headers["cache-control"] == "private, no-store"


def test_report_html_escapes_untrusted_strings(monkeypatch, tmp_path):
    monkeypatch.setattr("services.report_html_generator.get_report_dir", lambda: tmp_path)
    malicious = "</script><script>alert(1)</script>"
    report = {
        "account_name": "<script>alert(1)</script>",
        "summary": {},
        "positions": [{"ticker": malicious, "name": malicious}],
        "news": [{"title": malicious, "link": "javascript:alert(1)"}],
        "gemini_analysis": {"success": False, "one_line_summary": malicious},
    }
    path = ReportHtmlGenerator(AppConfig().morning_report).generate_html(report)
    content = path.read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in content
    assert "javascript:alert(1)" not in content
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in content


def test_workflow_has_no_pages_deployment_and_uses_private_url(monkeypatch):
    workflow = Path(".github/workflows/morning_report.yml").read_text(encoding="utf-8")
    assert "upload-pages-artifact" not in workflow
    assert "deploy-pages" not in workflow
    assert "contents: read" in workflow
    monkeypatch.delenv("RETIREMENT_PORTFOLIO_REPORT_URL", raising=False)
    monkeypatch.setenv("RETIREMENT_PORTFOLIO_WEB_URL", "https://app.example/")
    assert get_report_url() == "https://app.example/?view=report"


def test_operational_clients_do_not_disable_tls_verification():
    paths = [Path("services/kakao_service.py"), Path("services/gemini_service.py")]
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert "_create_unverified_context" not in source
    assert "CERT_NONE" not in source
    assert "check_hostname = False" not in source


def test_signed_report_link_serves_only_signed_owner(monkeypatch):
    monkeypatch.setenv("OAUTH_TOKEN_ENCRYPTION_KEY", "test-report-signing-key")
    captured = {}

    class FakeRepository:
        def __init__(self, user_id):
            captured["user_id"] = user_id
        def get_latest_morning_report(self):
            return type("Report", (), {"html_content": "<h1>signed private report</h1>"})()

    monkeypatch.setattr(web_app, "Repository", FakeRepository)
    token = web_app._morning_report_link_serializer().dumps({
        "user_id": "user-a",
        "purpose": "morning-report",
    })
    response = web_app.open_signed_morning_report(token)
    assert captured["user_id"] == "user-a"
    assert "signed private report" in response.body.decode()
    assert response.headers["cache-control"] == "private, no-store"


def test_signed_report_link_rejects_tampering(monkeypatch):
    monkeypatch.setenv("OAUTH_TOKEN_ENCRYPTION_KEY", "test-report-signing-key")
    token = web_app._morning_report_link_serializer().dumps({
        "user_id": "user-a",
        "purpose": "morning-report",
    })
    with pytest.raises(HTTPException) as exc_info:
        web_app.open_signed_morning_report(token + "tampered")
    assert exc_info.value.status_code == 404
