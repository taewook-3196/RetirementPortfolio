"""Render a privacy-safe administrator notification without sending it."""
from __future__ import annotations

from scripts.morning_report_admin_alert import classify_admin_alert

_KOREAN = {
    "no_eligible_recipients_verify_configuration": "발송 대상 설정 확인 필요",
    "delivery_marker_missing": "일부 발송 완료 기록 확인 불가",
    "schedule_missing_manual_run_present_delivery_markers_complete": "예약 실행 누락, 수동 복구 기록 확인",
    "schedule_missing_but_delivery_markers_complete": "예약 실행 누락, 발송 기록은 존재",
    "no_scheduled_runs": "예약 실행 기록 없음",
    "scheduled_runs_completed_without_success": "예약 실행 실패",
    "scheduled_run_in_progress": "예약 실행이 아직 진행 중",
}


def format_admin_alert(result: dict) -> str | None:
    """Only render aggregate audit codes; never echo arbitrary source fields."""
    alert = classify_admin_alert(result)
    if not alert["should_alert"]:
        return None
    reasons = alert["reason"].split(",")
    labels = [_KOREAN.get(reason, "추가 점검 필요") for reason in reasons]
    return (
        "[RetirementPortfolio 모닝 리포트 점검]\n"
        f"기준일(KST): {alert['date_kst']}\n"
        "상태: 관리자 확인 필요\n"
        + "\n".join(f"- {label}" for label in labels)
        + "\n자동 재발송은 실행하지 않았습니다."
    )
