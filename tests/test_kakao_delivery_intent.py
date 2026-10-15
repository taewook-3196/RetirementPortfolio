import pytest

from services.kakao_delivery_intent import ReportAction, resolve_report_intent


@pytest.mark.parametrize("legacy_sent", [True, False])
@pytest.mark.parametrize("claim", [True, False])
def test_forced_regeneration_never_resends_already_delivered_kakao(legacy_sent, claim):
    intent = resolve_report_intent(
        force_regenerate=True, kakao_enabled=True, existing_report=True,
        legacy_sent=legacy_sent, delivery_claim_available=claim,
    )
    if legacy_sent:
        assert intent.action == ReportAction.GENERATE_ONLY
    else:
        assert intent.action == (ReportAction.GENERATE_AND_ATTEMPT_CLAIM if claim else ReportAction.GENERATE_ONLY)


def test_force_regenerate_without_claim_generates_only():
    result = resolve_report_intent(
        force_regenerate=True, kakao_enabled=True, existing_report=True,
        legacy_sent=False, delivery_claim_available=False,
    )
    assert result.action == ReportAction.GENERATE_ONLY


def test_force_regenerate_with_eligibility_hint_allows_claim_attempt():
    result = resolve_report_intent(
        force_regenerate=True, kakao_enabled=True, existing_report=True,
        legacy_sent=False, delivery_claim_available=True,
    )
    assert result.action == ReportAction.GENERATE_AND_ATTEMPT_CLAIM


@pytest.mark.parametrize("force", [False, True])
def test_disabled_kakao_never_sends(force):
    result = resolve_report_intent(
        force_regenerate=force, kakao_enabled=False, existing_report=False,
        legacy_sent=False, delivery_claim_available=True,
    )
    assert result.action == ReportAction.GENERATE_ONLY


def test_existing_report_not_regenerated_without_force():
    result = resolve_report_intent(
        force_regenerate=False, kakao_enabled=True, existing_report=True,
        legacy_sent=False, delivery_claim_available=True,
    )
    assert result.action == ReportAction.SKIP


@pytest.mark.parametrize("unknown", [None, "false", 0, 1])
def test_unknown_claim_state_fails_closed(unknown):
    result = resolve_report_intent(
        force_regenerate=True, kakao_enabled=True, existing_report=True,
        legacy_sent=False, delivery_claim_available=unknown,
    )
    assert result.action == ReportAction.SKIP


def test_inconsistent_legacy_marker_fails_closed():
    result = resolve_report_intent(
        force_regenerate=True, kakao_enabled=True, existing_report=False,
        legacy_sent=True, delivery_claim_available=True,
    )
    assert result.action == ReportAction.SKIP


@pytest.mark.parametrize("force_regenerate", [False, True])
@pytest.mark.parametrize("kakao_enabled", [False, True])
@pytest.mark.parametrize("existing_report", [False, True])
@pytest.mark.parametrize("legacy_sent", [False, True])
@pytest.mark.parametrize("delivery_claim_available", [False, True])
def test_intent_full_boolean_matrix_never_resends_sent_or_disabled(
    force_regenerate, kakao_enabled, existing_report, legacy_sent,
    delivery_claim_available,
):
    intent = resolve_report_intent(
        force_regenerate=force_regenerate,
        kakao_enabled=kakao_enabled,
        existing_report=existing_report,
        legacy_sent=legacy_sent,
        delivery_claim_available=delivery_claim_available,
    )
    if legacy_sent or not kakao_enabled or not delivery_claim_available:
        assert intent.action != ReportAction.GENERATE_AND_ATTEMPT_CLAIM
    if existing_report and not force_regenerate:
        assert intent.action == ReportAction.SKIP
    if legacy_sent and not existing_report:
        assert intent.action == ReportAction.SKIP


@pytest.mark.parametrize("field", [
    "force_regenerate", "kakao_enabled", "existing_report",
    "legacy_sent", "delivery_claim_available",
])
@pytest.mark.parametrize("invalid", [None, "true", 1, [], {}])
def test_invalid_intent_inputs_never_authorize_send(field, invalid):
    args = dict(
        force_regenerate=True, kakao_enabled=True, existing_report=True,
        legacy_sent=False, delivery_claim_available=True,
    )
    args[field] = invalid
    assert resolve_report_intent(**args).action == ReportAction.SKIP


def test_claim_attempt_intent_cannot_bypass_durable_gateway(monkeypatch):
    """Policy eligibility must not become direct permission to send Kakao."""
    from datetime import date
    from uuid import uuid4
    from services.kakao_delivery_staged import run_staged_delivery
    from services.kakao_delivery_orchestrator import SendOutcome

    intent = resolve_report_intent(
        force_regenerate=True, kakao_enabled=True, existing_report=True,
        legacy_sent=False, delivery_claim_available=True,
    )
    assert intent.action == ReportAction.GENERATE_AND_ATTEMPT_CLAIM

    class DeniedClaim:
        def __init__(self, engine):
            pass

        def claim(self, attempt):
            return None

        def finish(self, attempt, status):
            pytest.fail("denied claim must never be finalized")

        def finish_sent_with_legacy(self, attempt):
            pytest.fail("denied claim must never be finalized")

    monkeypatch.setattr(
        "services.kakao_delivery_staged.PostgresDeliveryAttempts", DeniedClaim
    )
    result = run_staged_delivery(
        engine=None, user_id=uuid4(), report_date=date(2026, 10, 14),
        transport=lambda: pytest.fail("policy eligibility bypassed database claim"),
        env={"KAKAO_DELIVERY_STATE_ENABLED": "true", "KAKAO_DELIVERY_CUTOVER_APPROVED": "true"},
    )
    assert result.outcome == SendOutcome.NOT_CLAIMED
