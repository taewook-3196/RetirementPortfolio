"""Do not compare trailing PE against a forward-PE sector median."""
from services.sector_value_screening_service import _score


def test_trailing_only_pe_is_displayed_but_not_relative_valued():
    row = _score({"trailingPE": 10, "returnOnEquity": 0.2}, sector_pe_median=20)
    assert row["metrics"]["pe"] == 10
    assert row["metrics"]["pe_basis"] == "trailing"
    assert row["metrics"]["pe_discount_pct"] is None
    assert row["checks"]["reasonable_pe"] is None


def test_forward_pe_can_be_compared_with_forward_median():
    row = _score({"forwardPE": 10, "trailingPE": 30}, sector_pe_median=20)
    assert row["metrics"]["pe_basis"] == "forward"
    assert row["metrics"]["pe_discount_pct"] == 50.0
    assert row["checks"]["reasonable_pe"] is True
