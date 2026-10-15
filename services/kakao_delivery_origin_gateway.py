"""Staged-only common entrypoint for scheduled, manual, CLI, and cached sends.

This is not wired into production. Eligibility is an advisory fail-closed
precheck; only a committed PostgreSQL claim authorizes Kakao transport.
"""
from datetime import date
from ipaddress import ip_address
from uuid import UUID
from urllib.parse import urlsplit

from services.kakao_delivery_eligibility import check_delivery_eligibility
from services.kakao_delivery_feature_gate import evaluate_delivery_feature_gate
from services.kakao_delivery_orchestrator import SendOutcome, SendResult
from services.kakao_delivery_transport_adapter import send_staged_morning_report


def send_staged_for_origin(*, origin, engine, user_id, report_date, kakao_service,
                           summary_text, report_web_url, legacy_sent,
                           attempt_state, force=False, env=None):
    """Unify origin policy while preserving the authoritative database gate."""
    if not evaluate_delivery_feature_gate(env).enabled:
        return SendResult(SendOutcome.DISABLED)
    # Validate trusted routing identity before any service or database access.
    # bool is an int subclass, so require exact date and UUID types.
    if not isinstance(user_id, UUID) or type(report_date) is not date:
        return SendResult(SendOutcome.NOT_CLAIMED)
    if not isinstance(summary_text, str) or not summary_text.strip():
        return SendResult(SendOutcome.NOT_CLAIMED)
    if not isinstance(report_web_url, str):
        return SendResult(SendOutcome.NOT_CLAIMED)
    try:
        parsed = urlsplit(report_web_url)
        host = parsed.hostname
        if (
            parsed.scheme != "https" or not host or parsed.username is not None
            or parsed.password is not None or parsed.fragment
            or any(ord(ch) < 33 or ord(ch) == 127 for ch in report_web_url)
            or host.lower() in ("localhost", "localhost.localdomain")
            or host.endswith(".localhost")
            or host.startswith("127.") or host in ("0.0.0.0", "::1")
        ):
            return SendResult(SendOutcome.NOT_CLAIMED)
        _ = parsed.port
        try:
            parsed_ip = ip_address(host)
        except ValueError:
            parsed_ip = None
        if parsed_ip is not None and not parsed_ip.is_global:
            return SendResult(SendOutcome.NOT_CLAIMED)
    except ValueError:
        return SendResult(SendOutcome.NOT_CLAIMED)
    eligibility = check_delivery_eligibility(
        origin=origin, legacy_sent=legacy_sent,
        attempt_state=attempt_state, force=force,
    )
    if not eligibility.allowed:
        return SendResult(SendOutcome.NOT_CLAIMED)
    return send_staged_morning_report(
        engine=engine, user_id=user_id, report_date=report_date,
        kakao_service=kakao_service, summary_text=summary_text,
        report_web_url=report_web_url, env=env,
    )
