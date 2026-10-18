from pathlib import Path


def test_opening_snapshot_uses_stable_local_iso_date_not_locale_string():
    source = Path("web/app.py").read_text(encoding="utf-8")
    start = source.index('const openingPanel = document.createElement("details");')
    end = source.index("openingPanel.appendChild(openingForm);", start)
    body = source[start:end]
    assert 'const openingTodayLocalISO = () =>' in body
    assert 'now.getFullYear()' in body
    assert 'now.getMonth() + 1' in body
    assert 'now.getDate()' in body
    assert 'openingDate.max = openingTodayLocalISO()' in body
    assert 'openingDate.value > openingTodayLocalISO()' in body
    assert 'toLocaleDateString("en-CA")' not in body
