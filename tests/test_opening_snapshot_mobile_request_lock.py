from pathlib import Path


def test_opening_snapshot_load_save_are_mutually_exclusive_and_load_cannot_overwrite_edits():
    source = Path("web/app.py").read_text(encoding="utf-8")
    start = source.index('const openingPanel = document.createElement("details");')
    end = source.index("openingPanel.appendChild(openingForm);", start)
    body = source[start:end]
    assert "let openingRequestBusy = false;" in body
    assert "if (openingRequestBusy) return;" in body
    assert "if (openingRequestBusy || openingDraftConfirmed) return;" in body
    assert body.count("setOpeningRequestBusy(true);") == 2
    assert body.count("setOpeningRequestBusy(false);") == 2
    assert "if (loadEditVersion !== openingEditVersion)" in body
    assert "openingDraftConfirmed = snapshot.status === \"confirmed\";" in body
    assert "openingSave.disabled = busy || openingDraftConfirmed;" in body
