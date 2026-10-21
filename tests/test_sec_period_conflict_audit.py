from services.sec_period_conflict_audit import audit_sec_period_conflicts


def test_different_filing_values_for_same_period_flagged():
    equity = [
        {"period_end": "2024-12-31", "equity_usd": 100},
        {"period_end": "2024-12-31", "equity_usd": 105},
        {"period_end": "2025-03-31", "equity_usd": 110},
    ]
    bps = [
        {"period_end": "2024-12-31", "bps_unadjusted_usd": 10},
        {"period_end": "2024-12-31", "bps_unadjusted_usd": 10.5},
    ]
    result = audit_sec_period_conflicts(equity, bps)
    assert result["equity_conflicting_periods"] == ["2024-12-31"]
    assert result["bps_conflicting_periods"] == ["2024-12-31"]
    assert result["conflicting_period_count"] == 1
    assert result["investment_ready"] is False


def test_identical_repeat_values_not_flagged():
    result = audit_sec_period_conflicts(
        [{"period_end": "2024-12-31", "equity_usd": 100}] * 2,
        [{"period_end": "2024-12-31", "bps_unadjusted_usd": 10}] * 2,
    )
    assert result["conflicting_period_count"] == 0
