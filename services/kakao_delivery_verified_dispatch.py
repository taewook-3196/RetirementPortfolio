"""Staged-only verified dispatcher shared by every Kakao delivery origin.

This module is deliberately not imported by live services, scripts, or web
routes. A read-only preflight never replaces the atomic PostgreSQL claim.
"""
from datetime import date
from uuid import UUID

from services.kakao_delivery_cached_identity import verify_cached_report_identity
from services.kakao_delivery_eligibility import DeliveryOrigin
from services.kakao_delivery_feature_gate import evaluate_delivery_feature_gate
from services.kakao_delivery_origin_gateway import send_staged_for_origin
from services.kakao_delivery_orchestrator import SendOutcome, SendResult


def dispatch_verified_staged_report(*, origin, engine, user_id, report_date,
                                    kakao_service, summary_text, report_web_url,
                                    force=False, env=None):
    """Use the same persisted identity and claim for all four origins.

    Database read failures propagate rather than falling back to an unguarded
    Kakao send. Force can regenerate content, never override a delivery claim.
    """
    if not evaluate_delivery_feature_gate(env).enabled:
        return SendResult(SendOutcome.DISABLED)
    if not isinstance(origin, DeliveryOrigin) or type(force) is not bool:
        return SendResult(SendOutcome.NOT_CLAIMED)
    # Validate the payload before any database read or provider interaction.
    # The origin gateway independently rechecks these fields before claiming.
    if not isinstance(user_id, UUID) or type(report_date) is not date:
        return SendResult(SendOutcome.NOT_CLAIMED)
    if not isinstance(summary_text, str) or not summary_text.strip():
        return SendResult(SendOutcome.NOT_CLAIMED)
    if not isinstance(report_web_url, str) or not report_web_url.strip():
        return SendResult(SendOutcome.NOT_CLAIMED)
    identity = verify_cached_report_identity(
        engine=engine, user_id=user_id, report_date=report_date,
    )
    if identity is None:
        return SendResult(SendOutcome.NOT_CLAIMED)
    return send_staged_for_origin(
        origin=origin, engine=engine, user_id=identity.user_id,
        report_date=identity.report_date, kakao_service=kakao_service,
        summary_text=summary_text, report_web_url=report_web_url,
        legacy_sent=identity.legacy_sent,
        attempt_state=identity.attempt_state,
        force=force, env=env,
    )
