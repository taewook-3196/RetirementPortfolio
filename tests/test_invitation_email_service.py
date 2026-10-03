from services import invitation_email_service as email_service


def test_invitation_email_requires_server_configuration(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("INVITE_EMAIL_FROM", raising=False)
    assert email_service.invitation_email_configured() is False
    try:
        email_service.send_invitation_email(
            recipient="member@example.com",
            invite_url="https://retirementportfolio.onrender.com/#invite=test",
            expires_at="2026-10-10T00:00:00+00:00",
        )
        assert False, "expected configuration error"
    except email_service.InvitationEmailError:
        pass


def test_invitation_email_payload_does_not_log_or_persist_secret(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "server-only-test-key")
    monkeypatch.setenv("INVITE_EMAIL_FROM", "RetirementPortfolio <invite@example.com>")
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return b'{"id":"email-test-id"}'

    def fake_urlopen(request, timeout=0):
        captured["authorization"] = request.headers.get("Authorization")
        captured["body"] = request.data.decode("utf-8")
        return FakeResponse()

    monkeypatch.setattr(email_service.urllib.request, "urlopen", fake_urlopen)
    message_id = email_service.send_invitation_email(
        recipient="member@example.com",
        invite_url="https://retirementportfolio.onrender.com/#invite=one-time-secret",
        expires_at="2026-10-10T00:00:00+00:00",
    )
    assert message_id == "email-test-id"
    assert captured["authorization"] == "Bearer server-only-test-key"
    assert "one-time-secret" in captured["body"]
