"""
tests/test_github_service.py
GitHub Actions 클라우드 원격 제어 서비스 단위 테스트.
"""

import json
import pytest
from unittest.mock import MagicMock, patch
import urllib.error

from core.config import AppConfig, MorningReportConfig, ETFConfig
from services.github_service import GitHubService


@pytest.fixture(autouse=True)
def mock_save_config():
    with patch("services.github_service.save_config") as m:
        yield m


@pytest.fixture
def sample_config():
    return AppConfig(
        etfs=[ETFConfig(ticker="069500", name="KODEX 200", target_weight=1.0)],
        morning_report=MorningReportConfig(
            github_repo="testowner/testrepo",
            github_token="ghp_testtoken12345",
            github_workflow_id="morning_report.yml",
            github_cloud_enabled=False,
        )
    )


def test_is_configured():
    cfg_empty = AppConfig(morning_report=MorningReportConfig())
    svc_empty = GitHubService(cfg_empty)
    assert not svc_empty.is_configured()

    cfg_valid = AppConfig(
        morning_report=MorningReportConfig(
            github_repo="owner/repo",
            github_token="ghp_xxxx"
        )
    )
    svc_valid = GitHubService(cfg_valid)
    assert svc_valid.is_configured()


@patch("urllib.request.urlopen")
def test_get_workflow_status_active(mock_urlopen, sample_config):
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps({"state": "active"}).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    svc = GitHubService(sample_config)
    ok, desc, data = svc.get_workflow_status()

    assert ok is True
    assert "활성화" in desc
    assert sample_config.morning_report.github_cloud_enabled is True


@patch("urllib.request.urlopen")
def test_enable_workflow_success(mock_urlopen, sample_config):
    mock_resp = MagicMock()
    mock_resp.status = 204
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    svc = GitHubService(sample_config)
    ok, msg = svc.enable_workflow()

    assert ok is True
    assert "성공적" in msg
    assert sample_config.morning_report.github_cloud_enabled is True


@patch("urllib.request.urlopen")
def test_disable_workflow_success(mock_urlopen, sample_config):
    sample_config.morning_report.github_cloud_enabled = True
    mock_resp = MagicMock()
    mock_resp.status = 204
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    svc = GitHubService(sample_config)
    ok, msg = svc.disable_workflow()

    assert ok is True
    assert "비활성화" in msg
    assert sample_config.morning_report.github_cloud_enabled is False


@patch("urllib.request.urlopen")
def test_trigger_workflow_dispatch_success(mock_urlopen, sample_config):
    mock_resp = MagicMock()
    mock_resp.status = 204
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    svc = GitHubService(sample_config)
    ok, msg = svc.trigger_workflow_dispatch()

    assert ok is True
    assert "신호를 전송" in msg


@patch("urllib.request.urlopen")
def test_http_error_handling(mock_urlopen, sample_config):
    error_fp = MagicMock()
    error_fp.read.return_value = b'{"message": "Bad credentials"}'
    mock_urlopen.side_effect = urllib.error.HTTPError(
        url="https://api.github.com",
        code=401,
        msg="Unauthorized",
        hdrs={},
        fp=error_fp,
    )

    svc = GitHubService(sample_config)
    ok, msg = svc.enable_workflow()

    assert ok is False
    assert "401" in msg
