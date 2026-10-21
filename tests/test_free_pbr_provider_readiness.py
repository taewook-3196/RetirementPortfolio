from services.free_pbr_provider_readiness import free_provider_readiness


def test_unverified_provider_never_ready():
    result = free_provider_readiness("us")
    assert result["status"] == "withheld"
    assert len(result["missing"]) == 4


def test_all_external_checks_required():
    result = free_provider_readiness("kr", fundamentals_verified=True,
                                     price_history_verified=True, license_reviewed=True)
    assert result["status"] == "withheld"
    assert result["missing"] == ["corporate_actions_verified"]


def test_verified_pilot_only():
    result = free_provider_readiness("us", fundamentals_verified=True,
                                     price_history_verified=True, license_reviewed=True,
                                     corporate_actions_verified=True)
    assert result["status"] == "pilot_ready"
    assert result["plan"]["pilot_tickers"] == ("AAPL", "MSFT", "JNJ")


def test_unknown_market_blocked():
    assert free_provider_readiness("unknown")["status"] == "withheld"
