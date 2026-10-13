"""외부에 노출되는 Web 및 Morning Report URL을 안전하게 결정합니다."""

from __future__ import annotations

import os
from urllib.parse import urlparse


DEFAULT_WEB_APP_URL = "https://retirementportfolio.onrender.com/"
DEFAULT_REPORT_URL = "https://taewook-3196.github.io/RetirementPortfolio/"


def validate_public_url(value: str | None, fallback: str) -> str:
    """Return a normalized HTTP(S) public URL, or the supplied safe fallback."""
    candidate = (value or "").strip()
    parsed = urlparse(candidate)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
        candidate = fallback
    return candidate.rstrip("/") + "/"


def get_web_app_url() -> str:
    """보고서와 웹 deep link가 공유하는 공개 웹앱 URL을 반환합니다."""
    return validate_public_url(
        os.getenv("RETIREMENT_PORTFOLIO_WEB_URL"),
        DEFAULT_WEB_APP_URL,
    )


def get_report_url() -> str:
    """Return the configured public Morning Report URL with legacy fallbacks."""
    explicit_url = os.getenv("RETIREMENT_PORTFOLIO_REPORT_URL")
    if explicit_url and explicit_url.strip():
        return validate_public_url(explicit_url, DEFAULT_REPORT_URL)

    legacy_url = os.getenv("GITHUB_PAGES_BASE_URL")
    if legacy_url and legacy_url.strip():
        return validate_public_url(legacy_url, DEFAULT_REPORT_URL)

    repository = os.getenv("GITHUB_REPOSITORY", "").strip()
    if "github.com/" in repository:
        repository = repository.split("github.com/", 1)[1].strip("/").removesuffix(".git")
    parts = repository.split("/", 2)
    if len(parts) == 2 and all(part.strip() for part in parts):
        owner, repo = (part.strip() for part in parts)
        return validate_public_url(
            f"https://{owner.lower()}.github.io/{repo}/",
            DEFAULT_REPORT_URL,
        )

    return DEFAULT_REPORT_URL
