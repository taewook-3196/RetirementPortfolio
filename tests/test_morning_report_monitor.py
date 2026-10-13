"""배포된 Morning Report 자동 감시기의 회귀 테스트."""

import datetime as dt
from io import BytesIO
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.monitor_morning_report import KST, monitor_report_url
from scripts.verify_morning_report_artifact import REQUIRED_FRAGMENTS


class FakeResponse:
    def __init__(self, content: str, *, status: int = 200, url: str = "https://report.example/"):
        self._body = BytesIO(content.encode("utf-8"))
        self.status = status
        self.headers = {"Content-Length": str(len(content.encode("utf-8")))}
        self._url = url

    def read(self, size=-1):
        return self._body.read(size)

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


def _report(date_text="2026-10-13"):
    required = "\n".join(REQUIRED_FRAGMENTS)
    return f"<title>모닝 포트폴리오 리포트 | {date_text}</title>\n{required}"


def _opener(response):
    def open_request(request, timeout):
        assert request.full_url == "https://report.example/"
        assert timeout == 20
        return response

    return open_request


def test_monitor_accepts_fresh_complete_report():
    result = monitor_report_url(
        "https://report.example",
        now=dt.datetime(2026, 10, 13, 7, tzinfo=KST),
        opener=_opener(FakeResponse(_report())),
    )

    assert result["status"] == "ok"
    assert result["report_date"] == "2026-10-13"
    assert result["age_hours"] == 7.0
    assert result["size_bytes"] > 0


def test_monitor_rejects_stale_report():
    with pytest.raises(RuntimeError, match="오래되었습니다"):
        monitor_report_url(
            "https://report.example/",
            now=dt.datetime(2026, 10, 13, 12, tzinfo=KST),
            max_age_hours=36,
            opener=_opener(FakeResponse(_report("2026-10-11"))),
        )


def test_monitor_rejects_missing_report_features():
    with pytest.raises(RuntimeError, match="필수 보고서 기능"):
        monitor_report_url(
            "https://report.example/",
            now=dt.datetime(2026, 10, 13, 7, tzinfo=KST),
            opener=_opener(FakeResponse(_report().replace(REQUIRED_FRAGMENTS[0], ""))),
        )


def test_monitor_rejects_secret_marker():
    with pytest.raises(RuntimeError, match="secret 관련 문자열"):
        monitor_report_url(
            "https://report.example/",
            now=dt.datetime(2026, 10, 13, 7, tzinfo=KST),
            opener=_opener(FakeResponse(_report() + "\nDATABASE_URL")),
        )


def test_monitor_rejects_non_success_status():
    with pytest.raises(RuntimeError, match="HTTP 상태"):
        monitor_report_url(
            "https://report.example/",
            now=dt.datetime(2026, 10, 13, 7, tzinfo=KST),
            opener=_opener(FakeResponse(_report(), status=503)),
        )


def test_monitor_rejects_future_report_date():
    with pytest.raises(RuntimeError, match="현재보다 미래"):
        monitor_report_url(
            "https://report.example/",
            now=dt.datetime(2026, 10, 13, 7, tzinfo=KST),
            opener=_opener(FakeResponse(_report("2026-10-14"))),
        )


def test_monitor_rejects_oversized_report():
    response = FakeResponse(_report())
    response.headers["Content-Length"] = str(6 * 1024 * 1024)
    with pytest.raises(RuntimeError, match="허용 크기"):
        monitor_report_url(
            "https://report.example/",
            now=dt.datetime(2026, 10, 13, 7, tzinfo=KST),
            opener=_opener(response),
        )


def test_monitor_workflow_has_bounded_retries_and_deduplicated_alerts():
    workflow = Path(".github/workflows/morning_report_monitor.yml").read_text(
        encoding="utf-8",
    )

    assert "workflow_run:" in workflow
    assert "cron: '0 23 * * *'" in workflow
    assert "for attempt in 1 2 3" in workflow
    assert "issues: write" in workflow
    assert "handleFailure" in workflow
    assert "handleRecovery" in workflow
    assert "secrets." not in workflow


def test_monitor_cli_has_no_third_party_runtime_dependency():
    result = subprocess.run(
        [sys.executable, "-S", "-m", "scripts.monitor_morning_report", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "--max-age-hours" in result.stdout
