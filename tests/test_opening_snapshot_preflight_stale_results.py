from pathlib import Path


def test_preflight_results_are_invalidated_on_edits_and_draft_actions():
    source = Path("web/app.py").read_text(encoding="utf-8")
    start = source.index('const openingPanel = document.createElement("details");')
    end = source.index("openingPanel.appendChild(openingForm);", start)
    body = source[start:end]
    assert 'field.addEventListener("input", clearOpeningCheck)' in body
    assert 'field.addEventListener("change", clearOpeningCheck)' in body
    assert body.count("clearOpeningCheck();") >= 2
    assert "const checkVersion = ++openingCheckVersion;" in body
    assert body.count("if (checkVersion !== openingCheckVersion) return;") == 2
    assert 'openingCheckResult.textContent = "";' in body
