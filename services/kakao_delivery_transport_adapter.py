"""Staged-only adapter for the existing KakaoService transport contract.

Not imported by the production scheduler, UI, or CLI. It does not initiate
delivery itself: the durable claim must be granted by run_staged_delivery.
"""
from services.kakao_delivery_staged import run_staged_delivery


def send_staged_morning_report(*, engine, user_id, report_date, kakao_service,
                               summary_text, report_web_url, env=None):
    """Adapt KakaoService.send_morning_report without bypassing the DB claim."""
    if not callable(getattr(kakao_service, "send_morning_report", None)):
        raise TypeError("Kakao service must implement send_morning_report")
    return run_staged_delivery(
        engine=engine,
        user_id=user_id,
        report_date=report_date,
        transport=lambda: kakao_service.send_morning_report(summary_text, report_web_url),
        env=env,
    )
