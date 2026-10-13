"""배포된 Morning Report의 접근성, 최신성, 필수 기능 및 secret 노출을 감시합니다."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import urllib.request
from typing import Callable

from core.public_urls import get_report_url, validate_public_url
from scripts.verify_morning_report_artifact import verify_report_content


KST = dt.timezone(dt.timedelta(hours=9))
REPORT_DATE_PATTERN = re.compile(
    r"모닝 포트폴리오 리포트\s*\|\s*(\d{4}-\d{2}-\d{2})"
)
MAX_REPORT_BYTES = 5 * 1024 * 1024


def _read_response(response, max_bytes: int = MAX_REPORT_BYTES) -> bytes:
    content_length = response.headers.get("Content-Length")
    if content_length and int(content_length) > max_bytes:
        raise RuntimeError("배포된 Morning Report가 허용 크기를 초과했습니다.")

    payload = response.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise RuntimeError("배포된 Morning Report가 허용 크기를 초과했습니다.")
    return payload


def monitor_report_url(
    url: str,
    *,
    now: dt.datetime | None = None,
    max_age_hours: int = 36,
    opener: Callable = urllib.request.urlopen,
) -> dict:
    """배포 URL을 조회하여 보고서 기능과 KST 기준 최신성을 검사합니다."""
    safe_url = validate_public_url(url, get_report_url())
    request = urllib.request.Request(
        safe_url,
        headers={
            "Accept": "text/html",
            "Cache-Control": "no-cache",
            "User-Agent": "RetirementPortfolio-MorningReportMonitor/1.0",
        },
    )
    with opener(request, timeout=20) as response:
        status = getattr(response, "status", 200)
        if status != 200:
            raise RuntimeError(f"Morning Report HTTP 상태가 비정상입니다: {status}")
        final_url = validate_public_url(response.geturl(), safe_url)
        payload = _read_response(response)

    try:
        content = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("Morning Report가 UTF-8 HTML이 아닙니다.") from exc

    verify_report_content(content)
    match = REPORT_DATE_PATTERN.search(content)
    if not match:
        raise RuntimeError("Morning Report에서 기준 날짜를 찾을 수 없습니다.")

    report_date = dt.date.fromisoformat(match.group(1))
    checked_at = (now or dt.datetime.now(KST)).astimezone(KST)
    report_midnight = dt.datetime.combine(report_date, dt.time.min, tzinfo=KST)
    age_hours = (checked_at - report_midnight).total_seconds() / 3600
    if age_hours < -1:
        raise RuntimeError("Morning Report 날짜가 현재보다 미래입니다.")
    if age_hours > max_age_hours:
        raise RuntimeError(
            f"Morning Report가 오래되었습니다: {report_date.isoformat()} "
            f"({age_hours:.1f}시간 경과)"
        )

    return {
        "status": "ok",
        "url": final_url,
        "report_date": report_date.isoformat(),
        "checked_at": checked_at.isoformat(),
        "age_hours": round(age_hours, 1),
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=get_report_url())
    parser.add_argument("--max-age-hours", type=int, default=36)
    args = parser.parse_args()
    if args.max_age_hours <= 0:
        parser.error("--max-age-hours는 1 이상이어야 합니다.")

    result = monitor_report_url(
        args.url,
        max_age_hours=args.max_age_hours,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
