"""Staged-only cached Kakao entrypoint using persisted report identity.

Never imported by production CLI. Cache data alone cannot authorize transport.
"""
from services.kakao_delivery_cached_identity import verify_cached_report_identity
from services.kakao_delivery_eligibility import DeliveryOrigin
from services.kakao_delivery_feature_gate import evaluate_delivery_feature_gate
from services.kakao_delivery_origin_gateway import send_staged_for_origin
from services.kakao_delivery_orchestrator import SendOutcome, SendResult


def send_staged_cached_report(*, engine, user_id, report_date, kakao_service,
                              summary_text, report_web_url, env=None):
    """Fail closed on unknown report/attempt state; DB claim remains final gate."""
    if not evaluate_delivery_feature_gate(env).enabled:
        return SendResult(SendOutcome.DISABLED)
    # Any database error is propagated; callers must not fall back to legacy.
    identity = verify_cached_report_identity(
        engine=engine, user_id=user_id, report_date=report_date,
    )
    if identity is None:
        return SendResult(SendOutcome.NOT_CLAIMED)
    return send_staged_for_origin(
        origin=DeliveryOrigin.CACHED,
        engine=engine,
        user_id=identity.user_id,
        report_date=identity.report_date,
        kakao_service=kakao_service,
        summary_text=summary_text,
        report_web_url=report_web_url,
        legacy_sent=identity.legacy_sent,
        attempt_state=identity.attempt_state,
        force=False,
        env=env,
    )
