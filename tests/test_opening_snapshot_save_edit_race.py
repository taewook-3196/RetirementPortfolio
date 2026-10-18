from pathlib import Path


def test_opening_snapshot_save_distinguishes_concurrent_edits():
    source = Path("web/app.py").read_text(encoding="utf-8")
    start = source.index('const openingPanel = document.createElement("details");')
    end = source.index("openingPanel.appendChild(openingForm);", start)
    body = source[start:end]
    assert "const saveEditVersion = openingEditVersion;" in body
    assert body.count("saveEditVersion === openingEditVersion") == 2
    assert "이후 수정한 내용은 저장되지 않았습니다." in body
    assert "현재 수정한 내용은 유지됩니다." in body
    assert "setOpeningRequestBusy(false);" in body
