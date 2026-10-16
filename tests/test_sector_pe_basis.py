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



def test_extreme_forward_pe_is_visible_but_not_compared_to_filtered_benchmark():
    row = _score({"forwardPE": 250, "returnOnEquity": 0.2}, sector_pe_median=20)
    assert row["metrics"]["pe"] == 250
    assert row["metrics"]["pe_basis"] == "forward"
    assert row["metrics"]["pe_discount_pct"] is None
    assert row["checks"]["reasonable_pe"] is None


def test_nonpositive_trailing_pe_is_not_reported_as_valid_valuation():
    for trailing in (0, -12):
        row = _score({"trailingPE": trailing}, sector_pe_median=20)
        assert row["metrics"]["pe"] is None
        assert row["metrics"]["pe_basis"] is None
        assert row["metrics"]["pe_discount_pct"] is None


def test_upper_comparable_forward_pe_boundary():
    row = _score({"forwardPE": 200}, sector_pe_median=20)
    assert row["metrics"]["pe_discount_pct"] == -900.0
    assert row["checks"]["reasonable_pe"] is False


def test_financials_pbr_roe_label(monkeypatch):
    from services import sector_value_screening_service as svc
    monkeypatch.setattr(svc, "_fetch_info", lambda ticker: {"priceToBook": 1.0, "returnOnEquity": 0.1, "forwardPE": 12.0})
    svc.CACHE.clear()
    try:
        rows = svc.screen_sector("us", "financials")["results"]
        assert rows
        assert all(row["valuation_label"] == "PBR/ROE 상대가치 참고" for row in rows)
        assert all("PBR/ROE" in row["valuation_basis"] for row in rows)
    finally:
        svc.CACHE.clear()


def test_equal_scores_prefer_greater_metric_coverage(monkeypatch):
    from services import sector_value_screening_service as svc

    tickers = svc.UNIVERSE["us"]["technology"]
    first, second = tickers[:2]
    def fake_info(ticker):
        base = {"forwardPE": 10.0, "priceToBook": 2.0, "returnOnEquity": 0.2,
                "revenueGrowth": 0.1, "profitMargins": 0.2, "fiftyTwoWeekChange": 0.1}
        if ticker == first:
            return {"forwardPE": 10.0, "priceToBook": 2.0,
                    "returnOnEquity": 0.2, "revenueGrowth": 0.1}
        if ticker == second:
            return base
        return {"forwardPE": 10.0}
    monkeypatch.setattr(svc, "_fetch_info", fake_info)
    svc.CACHE.clear()
    try:
        rows = svc.screen_sector("us", "technology")["results"]
        assert rows[0]["ticker"] == second
        assert rows[0]["coverage"] == 6
    finally:
        svc.CACHE.clear()


def test_screen_ranking_accounts_for_missing_evidence(monkeypatch):
    from services import sector_value_screening_service as svc

    tickers = svc.UNIVERSE["us"]["technology"]
    partial, complete = tickers[:2]
    def fake_info(ticker):
        base = {"forwardPE": 10, "priceToBook": 2, "returnOnEquity": .2,
                "revenueGrowth": .1, "profitMargins": .2,
                "fiftyTwoWeekChange": -.1}
        if ticker == partial:
            return {"forwardPE": 10, "priceToBook": 2, "returnOnEquity": .2,
                    "revenueGrowth": .1}
        if ticker == complete:
            return base
        return {"forwardPE": 10}
    monkeypatch.setattr(svc, "_fetch_info", fake_info)
    svc.CACHE.clear()
    try:
        rows = svc.screen_sector("us", "technology")["results"]
        assert rows[0]["ticker"] == complete
        assert rows[0]["coverage"] == 6
        assert rows[0]["score"] < 100
        assert next(row for row in rows if row["ticker"] == partial)["score"] == 100
    finally:
        svc.CACHE.clear()
