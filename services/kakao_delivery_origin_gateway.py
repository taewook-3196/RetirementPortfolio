"""Staged-only common entrypoint for scheduled, manual, CLI, and cached sends.

This is not wired into production. Eligibility is an advisory fail-closed
precheck; only a committed PostgreSQL claim authorizes Kakao transport.
"""
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
