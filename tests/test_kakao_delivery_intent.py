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
        assert intent.action == (ReportAction.GENERATE_AND_SEND if claim else ReportAction.GENERATE_ONLY)


def test_force_regenerate_without_claim_generates_only():
    result = resolve_report_intent(
        force_regenerate=True, kakao_enabled=True, existing_report=True,
        legacy_sent=False, delivery_claim_available=False,
    )
    assert result.action == ReportAction.GENERATE_ONLY


def test_force_regenerate_with_authoritative_claim_allows_separate_delivery():
    result = resolve_report_intent(
        force_regenerate=True, kakao_enabled=True, existing_report=True,
        legacy_sent=False, delivery_claim_available=True,
    )
    assert result.action == ReportAction.GENERATE_AND_SEND


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
