"""Mobile opening snapshot draft form smoke checks."""
from pathlib import Path


def test_opening_snapshot_form_is_opt_in_and_safe():
    source = Path("web/app.py").read_text(encoding="utf-8")
    start = source.index('openingToggle.textContent = "계좌 시작 자산 입력 (초안)"')
    end = source.index("detailsPanel.appendChild(openingPanel);", start)
    form = source[start:end]
    assert 'openingLoad.addEventListener("click"' in form
    assert 'openingForm.addEventListener("submit"' in form
    assert 'method: "PUT"' in form
    assert "getAccountCurrency(account)" in form
    assert 'snapshot.status === "confirmed"' in form
    assert "기존 잔고에는 반영되지 않습니다." in form
    assert "innerHTML" not in form
