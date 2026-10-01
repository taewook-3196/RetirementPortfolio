"""GitHub Pages에 업로드하기 직전 아침 보고서 artifact를 검증합니다."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import os
from pathlib import Path


REQUIRED_FRAGMENTS = (
    'class="report-chart-toggle"',
    'id="report-chart-data"',
    'data-period="1M"',
    'data-period="3M"',
    'data-period="6M"',
    'data-period="1Y"',
    'data-period="ALL"',
    "BUY ▲",
    "SELL ▼",
    "계좌 · 거래 관리",
    "toggleReportChart(this)",
    "웹앱 상세보기",
)

FORBIDDEN_MARKERS = (
    "DATABASE_URL",
    "GEMINI_API_KEY",
    "KAKAO_ACCESS_TOKEN",
    "KAKAO_REFRESH_TOKEN",
    "GITHUB_TOKEN",
    "access_token",
    "refresh_token",
    "postgresql://",
    "postgres://",
)


def verify_report_artifact(directory: Path, report_date: str | None = None) -> dict:
    """현재 날짜 보고서와 index.html이 같은 최신 기능 HTML인지 검사합니다."""
    directory = Path(directory)
    index_path = directory / "index.html"
    date_key = report_date or datetime.datetime.now().strftime("%Y%m%d")
    dated_path = directory / f"morning_report_{date_key}.html"

    if not index_path.is_file():
        raise RuntimeError(f"Pages index.html이 없습니다: {index_path}")
    if not dated_path.is_file():
        raise RuntimeError(f"오늘자 보고서가 없습니다: {dated_path}")

    index_bytes = index_path.read_bytes()
    dated_bytes = dated_path.read_bytes()
    if index_bytes != dated_bytes:
        raise RuntimeError("index.html이 오늘자 보고서와 일치하지 않습니다.")

    content = index_bytes.decode("utf-8")
    missing = [fragment for fragment in REQUIRED_FRAGMENTS if fragment not in content]
    if missing:
        raise RuntimeError(
            "최종 index.html에 필수 보고서 기능이 없습니다: "
            + ", ".join(missing)
        )

    if '<a href="https://retirementportfolio.onrender.com/' in content and 'class="pos-name"' in content:
        raise RuntimeError("보유종목 주 클릭 영역이 아직 직접 링크로 렌더링됩니다.")

    forbidden = [marker for marker in FORBIDDEN_MARKERS if marker in content]
    for env_name in (
        "DATABASE_URL",
        "GEMINI_API_KEY",
        "KAKAO_ACCESS_TOKEN",
        "KAKAO_REFRESH_TOKEN",
        "GITHUB_TOKEN",
    ):
        value = os.getenv(env_name, "")
        if len(value) >= 8 and value in content:
            forbidden.append(env_name + " value")
    if forbidden:
        raise RuntimeError(
            "최종 index.html에 secret 관련 문자열이 포함되었습니다: "
            + ", ".join(sorted(set(forbidden)))
        )

    digest = hashlib.sha256(index_bytes).hexdigest()
    return {
        "index_path": str(index_path),
        "dated_path": str(dated_path),
        "size_bytes": len(index_bytes),
        "sha256": digest,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--directory",
        type=Path,
        default=Path("exports/reports"),
    )
    parser.add_argument("--date", default=None)
    args = parser.parse_args()

    result = verify_report_artifact(args.directory, args.date)
    print("Pages 보고서 artifact 검증 완료")
    for key, value in result.items():
        print(f"- {key}: {value}")


if __name__ == "__main__":
    main()
