"""Opening snapshot preflight API contract checks."""
from pathlib import Path


def test_preflight_endpoint_is_owner_scoped_read_only():
    source = Path("web/app.py").read_text(encoding="utf-8")
    start = source.index('@app.get("/api/accounts/{account_id}/opening-snapshot/preflight")')
    end = source.index('@app.get("/api/accounts/{account_id}/return-readiness")', start)
    body = source[start:end]
    assert "get_verified_user_id(authorization)" in body
    assert "account = repo.get_account(account_id)" in body
    assert "if account is None:" in body
    assert "account_currency=account.currency" in body
    assert "repo.get_opening_snapshot(account_id)" in body
    assert "check_opening_snapshot_confirmation(" in body
    assert "repo.get_cash_flows(account_id)" in body
    assert "repo.get_transactions(account_id=account_id)" in body
    assert "repo.get_dividends(account_id=account_id)" in body
    assert "save_opening_snapshot" not in body
