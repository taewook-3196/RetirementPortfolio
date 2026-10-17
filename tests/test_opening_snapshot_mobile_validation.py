"""Opening snapshot mobile input guard regression checks."""
from pathlib import Path


def test_opening_snapshot_ui_rejects_duplicate_and_invalid_values():
    source = Path("web/app.py").read_text(encoding="utf-8")
    start = source.index('openingToggle.textContent = "계좌 시작 자산 입력 (초안)"')
    end = source.index("detailsPanel.appendChild(openingPanel);", start)
    body = source[start:end]
    assert "const seenTickers = new Set()" in body
    assert "seenTickers.has(ticker)" in body
    assert "Number.isFinite(quantity)" in body
    assert "quantity === 0 && marketValue !== 0" in body
    assert "openingDate.value >" in body
    assert "openingCash.value.trim()" in body
    assert 'openingHelp.textContent = "예시:' in body
