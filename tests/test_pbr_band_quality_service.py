from datetime import date, timedelta
from services.pbr_band_quality_service import evaluate_pbr_band

def inputs():
    start = date(2019, 1, 1)
    return dict(
        observations=[((start + timedelta(days=100*i)).isoformat(), 0.8 + i*.02) for i in range(28)],
        current_pbr=1.1, source="verified-report-provider", as_of="2026-01-01",
        industry="industrials", current_bps=15, current_roe=.12,
        reporting_currency="USD", source_verified=True, accounting_consistent=True,
    )

def test_quality_gate_accepts_reference_only():
    result = evaluate_pbr_band(**inputs())
    assert result["status"] == "reference_only"
    assert result["data_quality"]["source_verified"] is True

def test_unverified_source_blocks_band():
    values = inputs()
    values["source_verified"] = False
    assert evaluate_pbr_band(**values)["status"] == "withheld"

def test_financial_and_intangible_industries_are_withheld():
    for industry in ("banks", "insurance", "software", "biotechnology"):
        values = inputs()
        values["industry"] = industry
        assert evaluate_pbr_band(**values)["status"] == "withheld"

def test_invalid_book_value_and_accounting_blocks_band():
    values = inputs()
    values["current_bps"] = -1
    assert evaluate_pbr_band(**values)["status"] == "withheld"
    values = inputs()
    values["accounting_consistent"] = False
    assert evaluate_pbr_band(**values)["status"] == "withheld"
