"""Draft-only opening snapshot persistence contract tests."""
from pathlib import Path


def test_opening_snapshot_draft_repository_is_owner_scoped():
    source = Path("database/repository.py").read_text(encoding="utf-8")
    start = source.index("    def save_opening_snapshot_draft(")
    end = source.index("    def get_default_account(", start)
    body = source[start:end]
    assert "Account.user_id == self.user_id" in body
    assert ".with_for_update()" in body
    assert 'snapshot.status == "confirmed"' in body
    assert 'snapshot.status = "draft"' in body
    assert "validate_opening_snapshot(" in body
    assert "AccountOpeningHolding(" in body


def test_opening_snapshot_read_is_owner_scoped():
    source = Path("database/repository.py").read_text(encoding="utf-8")
    start = source.index("    def get_opening_snapshot(")
    end = source.index("    def save_opening_snapshot_draft(", start)
    assert "Account.user_id == self.user_id" in source[start:end]
