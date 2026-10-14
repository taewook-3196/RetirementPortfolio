"""Pure, staged-only policy separating report generation from Kakao delivery.

This is not connected to production. Legacy force-resend remains unchanged
until an explicitly approved migration of every sender entrypoint.
"""
from dataclasses import dataclass
from enum import Enum


class ReportAction(str, Enum):
    SKIP = "skip"
    GENERATE_ONLY = "generate_only"
    GENERATE_AND_SEND = "generate_and_send"


@dataclass(frozen=True)
class ReportIntent:
    action: ReportAction
    reason: str


def resolve_report_intent(*, force_regenerate: bool, kakao_enabled: bool,
                          existing_report: bool, legacy_sent: bool,
                          delivery_claim_available: bool) -> ReportIntent:
    """Never turn a forced regeneration into implicit retransmission.

    delivery_claim_available is only a caller-provided eligibility hint.
    It is NOT proof of a committed claim and MUST NOT authorize transport.
    Actual dispatch always requires the staged gateway to obtain its own
    authoritative PostgreSQL claim before invoking transport.
    """
    if not all(type(value) is bool for value in (
        force_regenerate, kakao_enabled, existing_report,
        legacy_sent, delivery_claim_available,
    )):
        return ReportIntent(ReportAction.SKIP, "invalid or unknown delivery state")
    if legacy_sent and not existing_report:
        return ReportIntent(ReportAction.SKIP, "inconsistent legacy delivery state")
    if existing_report and not force_regenerate:
        return ReportIntent(ReportAction.SKIP, "existing report; do not implicitly resend")
    if not kakao_enabled:
        return ReportIntent(ReportAction.GENERATE_ONLY, "Kakao delivery disabled")
    if legacy_sent:
        return ReportIntent(ReportAction.GENERATE_ONLY, "legacy Kakao delivery already recorded")
    if not delivery_claim_available:
        return ReportIntent(ReportAction.GENERATE_ONLY, "no authoritative Kakao delivery claim")
    return ReportIntent(ReportAction.GENERATE_AND_SEND, "eligible for separately claimed delivery; no claim acquired")
