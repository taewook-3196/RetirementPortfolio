from pathlib import Path


def test_mobile_preflight_separates_blockers_and_warnings():
    source = Path("web/app.py").read_text(encoding="utf-8")
    start = source.index('const openingCheckResult = document.createElement("div");')
    end = source.index("openingPanel.appendChild(openingForm);", start)
    section = source[start:end]
    assert 'renderPreflightItems("확정 차단 사유", result.blockers)' in section
    assert 'renderPreflightItems("추가 확인 경고", result.warnings)' in section
    assert 'message.textContent = String(item.message || "기록 확인 필요")' in section
    assert 'openingCheckResult.setAttribute("aria-live", "polite")' in section
