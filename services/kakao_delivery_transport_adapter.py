"""Staged-only adapter for the existing KakaoService transport contract.

Not imported by the production scheduler, UI, or CLI. It does not initiate
delivery itself: the durable claim must be granted by run_staged_delivery.
"""
from services.kakao_delivery_staged import run_staged_delivery
from services.kakao_delivery_orchestrator import SendOutcome, SendResult


def send_staged_morning_report(*, engine, user_id, report_date, kakao_service,
                               summary_text, report_web_url, env=None):
    """Adapt KakaoService.send_morning_report without bypassing the DB claim."""
    # Validate local prerequisites before taking a durable claim. A missing
    # token or malformed service is a pre-transport error, not an uncertain send.
    if not callable(getattr(kakao_service, "send_morning_report", None)):
        raise TypeError("Kakao service must implement send_morning_report")
    if not callable(getattr(kakao_service, "is_configured", None)):
        raise TypeError("Kakao service must implement is_configured")
    if not kakao_service.is_configured():
        return SendResult(SendOutcome.FAILED_BEFORE_SEND)
    return run_staged_delivery(
        engine=engine,
        user_id=user_id,
        report_date=report_date,
        transport=lambda: kakao_service.send_morning_report(summary_text, report_web_url),
        env=env,
    )
