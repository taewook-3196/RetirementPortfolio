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
