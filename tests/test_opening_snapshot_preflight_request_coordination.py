from pathlib import Path


def test_preflight_cannot_start_while_draft_request_is_active():
    source = Path("web/app.py").read_text(encoding="utf-8")
    start = source.index('const openingPanel = document.createElement("details");')
    end = source.index("openingPanel.appendChild(openingForm);", start)
    body = source[start:end]
    assert "let openingCheckInFlight = false;" in body
    assert "openingCheck.disabled = busy || openingCheckInFlight;" in body
    assert "if (openingRequestBusy || openingCheckInFlight) return;" in body
    assert "openingCheckInFlight = true;" in body
    assert "openingCheckInFlight = false;" in body
    assert "openingCheck.disabled = openingRequestBusy;" in body
