import json
from unittest.mock import patch

from scripts.pilot_sec_companyfacts import fetch_sec_companyfacts, run_pilot


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, count):
        return json.dumps({"entityName": "Sample", "facts": {"us-gaap": {}, "dei": {}}}).encode()


def test_requires_real_contact_and_valid_cik():
    try:
        fetch_sec_companyfacts("bad", user_agent="Operator ops@domain.org")
        assert False
    except ValueError:
        pass
    try:
        fetch_sec_companyfacts("320193", user_agent="Operator ops@example.com")
        assert False
    except ValueError:
        pass


def test_request_uses_sec_endpoint_and_agent():
    with patch("scripts.pilot_sec_companyfacts.urlopen", return_value=FakeResponse()) as mocked:
        data = fetch_sec_companyfacts("320193", user_agent="Research ops@domain.org")
    assert data["entityName"] == "Sample"
    request = mocked.call_args.args[0]
    assert request.full_url.endswith("/CIK0000320193.json")
    assert request.get_header("User-agent") == "Research ops@domain.org"


def test_empty_realistic_response_is_not_misreported_as_ready():
    with patch("scripts.pilot_sec_companyfacts.fetch_sec_companyfacts",
               return_value={"entityName": "Sample", "facts": {"us-gaap": {}, "dei": {}}}):
        report = run_pilot("320193", user_agent="Research ops@domain.org", as_of="2025-12-31")
    assert report["strictly_matched_filings"] == 0
    assert report["match_audit"]["investment_ready"] is False
    assert report["match_audit"]["strict_match_count"] == 0
    assert report["coverage"]["investment_ready"] is False
