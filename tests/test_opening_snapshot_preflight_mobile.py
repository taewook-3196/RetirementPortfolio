"""Read-only opening snapshot preflight UI smoke checks."""
from pathlib import Path


def test_opening_snapshot_preflight_ui_is_read_only():
    source = Path("web/app.py").read_text(encoding="utf-8")
    start = source.index('openingCheck.textContent = "시작 자산 확정 전 검증"')
    end = source.index("openingPanel.appendChild(openingForm);", start)
    body = source[start:end]
    assert 'openingUrl + "/preflight"' in body
    assert 'renderPreflightItems("확정 차단 사유", result.blockers)' in body
    assert 'renderPreflightItems("추가 확인 경고", result.warnings)' in body
    assert "message.textContent" in body
    assert "최종 확정은 아직 지원하지 않습니다." in body
    assert 'method: "PUT"' not in body
