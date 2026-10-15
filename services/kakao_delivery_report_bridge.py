"""Staged report-service bridge, deliberately disconnected from production.

Integrators call this only after a report has been persisted. It maps the
existing report-service arguments to the verified claim-backed dispatcher and
never falls back to the legacy sender. No live code imports this module.
"""
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from services.kakao_delivery_eligibility import DeliveryOrigin
from services.kakao_delivery_orchestrator import SendOutcome
from services.kakao_delivery_verified_dispatch import dispatch_verified_staged_report


@dataclass(frozen=True)
class ReportDeliveryResult:
    ok: bool
    message: str
    outcome: SendOutcome


def send_persisted_report_staged(*, origin: DeliveryOrigin, engine,
                                 user_id: UUID, report_date: date,
                                 kakao_service, summary_text: str,
                                 report_web_url: str, force: bool = False,
                                 env=None) -> ReportDeliveryResult:
    """Adapt all report-service callsites to the durable delivery state.

    NOT_CLAIMED is not a success: it may indicate a sent/uncertain attempt,
    missing persisted report, or an invalid identity. In particular, callers
    must never retry using the legacy transport when this bridge returns false.
    """
    result = dispatch_verified_staged_report(
        origin=origin, engine=engine, user_id=user_id,
        report_date=report_date, kakao_service=kakao_service,
        summary_text=summary_text, report_web_url=report_web_url,
        force=force, env=env,
    )
    if result.outcome is SendOutcome.SENT:
        return ReportDeliveryResult(True, "카카오톡 발송 성공!", result.outcome)
    if result.outcome is SendOutcome.UNCERTAIN:
        return ReportDeliveryResult(
            False,
            "카카오톡 전송 결과가 불확실합니다. 자동 재발송하지 말고 관리자 확인이 필요합니다.",
            result.outcome,
        )
    if result.outcome is SendOutcome.NOT_CLAIMED:
        return ReportDeliveryResult(
            False, "발송 권한을 획득하지 못했습니다. 기존 발송 또는 보고서 상태를 확인하세요.",
            result.outcome,
        )
    if result.outcome is SendOutcome.FAILED_BEFORE_SEND:
        return ReportDeliveryResult(
            False, "카카오톡 전송 준비에 실패했습니다. 자동 우회 발송하지 않습니다.",
            result.outcome,
        )
    return ReportDeliveryResult(
        False, "신규 발송 기능이 비활성화되어 있습니다. 자동 우회 발송하지 않습니다.",
        result.outcome,
    )
