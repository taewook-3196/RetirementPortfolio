from datetime import date
from types import SimpleNamespace

from services.return_readiness import diagnose_return_readiness


def test_readiness_is_conservative_and_read_only():
    account = SimpleNamespace(currency="KRW", initial_capital=116_000_000)
    flow = SimpleNamespace(flow_date=date(2026, 1, 3), currency="KRW")
    trade = SimpleNamespace(transaction_date=date(2026, 1, 4))
    payout = SimpleNamespace(dividend_date=date(2026, 2, 1), currency="USD")
    result = diagnose_return_readiness(account, [flow], [trade], [payout])
    assert result["ready_for_xirr"] is False
    assert result["ready_for_twr"] is False
    assert result["counts"] == {"cash_flows": 1, "transactions": 1, "dividends": 1}
    codes = {warning["code"] for warning in result["warnings"]}
    assert {"OPENING_DATE_MISSING", "HISTORICAL_FX_UNVERIFIED", "VALUATION_HISTORY_UNVERIFIED"} <= codes
    assert account.initial_capital == 116_000_000


def test_readiness_with_empty_history_does_not_claim_return_is_available():
    result = diagnose_return_readiness(SimpleNamespace(currency="KRW"), [], [], [])
    assert result["ready_for_xirr"] is False
    assert result["ready_for_twr"] is False
    assert result["counts"]["transactions"] == 0
