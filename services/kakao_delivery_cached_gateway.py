"""Staged-only cached Kakao entrypoint using the shared verified dispatcher.

Never imported by production CLI. Cache data alone cannot authorize transport.
"""
from services.kakao_delivery_eligibility import DeliveryOrigin
from services.kakao_delivery_verified_dispatch import dispatch_verified_staged_report


def send_staged_cached_report(*, engine, user_id, report_date, kakao_service,
                              summary_text, report_web_url, env=None):
    """Delegate cached delivery to the same verified claim as other origins."""
    return dispatch_verified_staged_report(
        origin=DeliveryOrigin.CACHED,
        engine=engine, user_id=user_id, report_date=report_date,
        kakao_service=kakao_service, summary_text=summary_text,
        report_web_url=report_web_url, force=False, env=env,
    )
