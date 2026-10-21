import json
from scripts.pilot_sec_companyfacts_offline import audit_local_companyfacts


def test_offline_companyfacts_report(tmp_path):
    path = tmp_path / "sec.json"
    path.write_text(json.dumps({"cik": 320193, "entityName": "Example",
                                "facts": {"us-gaap": {}, "dei": {}}}), encoding="utf-8")
    result = audit_local_companyfacts(path, as_of="2025-12-31")
    assert result["cik"] == "0000320193"
    assert result["strictly_matched_filings"] == 0
    assert result["source_verified"] is False
    assert result["coverage"]["investment_ready"] is False


def test_offline_rejects_invalid_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"hello":"world"}', encoding="utf-8")
    try:
        audit_local_companyfacts(path, as_of="2025-12-31")
        assert False
    except ValueError:
        pass


def test_named_pilot_file_rejects_wrong_embedded_cik(tmp_path):
    path = tmp_path / "CIK0000320193.json"
    path.write_text(json.dumps({"cik": 789019, "entityName": "Other",
                                "facts": {"us-gaap": {}, "dei": {}}}), encoding="utf-8")
    try:
        audit_local_companyfacts(path, as_of="2025-12-31")
        assert False
    except ValueError as exc:
        assert "CIK" in str(exc)
