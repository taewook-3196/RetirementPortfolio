from unittest.mock import patch

from services.sec_connectivity_diagnostic import diagnose_sec_connectivity


def test_sec_diagnostic_dns_failure_does_not_probe_http():
    with patch("socket.getaddrinfo", side_effect=OSError("unavailable")):
        result = diagnose_sec_connectivity()
    assert result["dns"] == "failed"
    assert result["http"] == "not_tested"


def test_sec_diagnostic_does_not_send_http_without_contact():
    with patch("socket.getaddrinfo", return_value=[("x",)]), \
         patch("socket.create_connection") as conn, \
         patch.dict("os.environ", {"SEC_USER_AGENT": ""}):
        conn.return_value.__enter__.return_value = conn.return_value
        with patch("ssl.create_default_context") as context:
            context.return_value.wrap_socket.return_value.__enter__.return_value = object()
            result = diagnose_sec_connectivity()
    assert result["dns"] == "ok"
    assert result["tls"] == "ok"
    assert result["http"] == "skipped_missing_sec_user_agent"


def test_sec_diagnostic_uses_bounded_get_when_contact_is_configured():
    class Response:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, size=-1):
            assert size == 1
            return b"{"

    with patch("socket.getaddrinfo", return_value=[("x",)]), \
         patch("socket.create_connection") as conn, \
         patch.dict("os.environ", {"SEC_USER_AGENT": "RetirementPortfolio contact@valid-domain.org"}), \
         patch("ssl.create_default_context") as context, \
         patch("services.sec_connectivity_diagnostic.urlopen", return_value=Response()) as open_url:
        conn.return_value.__enter__.return_value = conn.return_value
        context.return_value.wrap_socket.return_value.__enter__.return_value = object()
        result = diagnose_sec_connectivity(timeout=1)
    assert result["http"] == "200"
    request = open_url.call_args.args[0]
    assert request.get_method() == "GET"
    assert request.get_header("User-agent") == "RetirementPortfolio contact@valid-domain.org"
