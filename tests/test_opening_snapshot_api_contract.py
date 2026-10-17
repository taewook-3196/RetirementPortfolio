"""Opening snapshot API security and compatibility checks."""
from pathlib import Path


def test_opening_snapshot_routes_require_account_ownership():
    source = Path("web/app.py").read_text(encoding="utf-8")
    start = source.index('class OpeningHoldingDraftRequest(BaseModel):')
    end = source.index('@app.get("/api/accounts/{account_id}/return-readiness")', start)
    body = source[start:end]
    assert '@app.get("/api/accounts/{account_id}/opening-snapshot")' in body
    assert '@app.put("/api/accounts/{account_id}/opening-snapshot")' in body
    assert body.count("get_verified_user_id(authorization)") == 3
    assert body.count("repo.get_account(account_id) is None") == 3
    assert "repo.save_opening_snapshot_draft(" in body
    assert "status_code=503" in body


def test_opening_snapshot_api_does_not_change_existing_cash_calculation():
    source = Path("web/app.py").read_text(encoding="utf-8")
    start = source.index('class OpeningHoldingDraftRequest(BaseModel):')
    end = source.index('@app.get("/api/accounts/{account_id}/return-readiness")', start)
    assert "get_cash_balance" not in source[start:end]
    assert "get_summary" not in source[start:end]
