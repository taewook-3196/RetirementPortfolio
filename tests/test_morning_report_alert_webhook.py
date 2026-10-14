import io
import json

import pytest

from scripts.morning_report_alert_webhook import send_admin_webhook


class Response:
    status = 204

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_webhook_posts_json_only_when_explicitly_invoked(monkeypatch):
    seen = []

    def fake_urlopen(request, timeout):
        seen.append((request.full_url, request.get_method(), json.loads(request.data), timeout))
        return Response()

    monkeypatch.setattr("scripts.morning_report_alert_webhook.urllib.request.urlopen", fake_urlopen)
    send_admin_webhook("점검 필요", url="https://alerts.example.com/hook")
    assert seen == [("https://alerts.example.com/hook", "POST", {"text": "점검 필요"}, 10)]


@pytest.mark.parametrize("url", [
    "http://alerts.example.com/hook",
    "https://127.0.0.1/hook",
    "https://10.0.0.1/hook",
    "https://user:secret@alerts.example.com/hook",
    "https://alerts.example.com/hook#fragment",
])
def test_unsafe_webhook_urls_are_rejected(url):
    with pytest.raises(ValueError):
        send_admin_webhook("alert", url=url)


def test_webhook_errors_do_not_leak_secret_url(monkeypatch):
    from urllib.error import URLError

    def fail(request, timeout):
        raise URLError("https://alerts.example.com/hook?token=PRIVATE_TOKEN")

    monkeypatch.setattr("scripts.morning_report_alert_webhook.urllib.request.urlopen", fail)
    with pytest.raises(RuntimeError) as exc:
        send_admin_webhook("alert", url="https://alerts.example.com/hook?token=PRIVATE_TOKEN")
    assert "PRIVATE_TOKEN" not in str(exc.value)
