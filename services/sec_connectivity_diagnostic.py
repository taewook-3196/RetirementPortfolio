"""Read-only SEC connectivity diagnostic; never downloads or stores filings."""
import os
import socket
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

HOST = "data.sec.gov"
URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"


def diagnose_sec_connectivity(timeout=5):
    result = {"host": HOST, "dns": "failed", "tls": "not_tested",
              "http": "not_tested", "sec_user_agent_configured": False}
    try:
        addresses = socket.getaddrinfo(HOST, 443, type=socket.SOCK_STREAM)
        if not addresses:
            return result
        result["dns"] = "ok"
    except (OSError, socket.gaierror):
        return result
    try:
        with socket.create_connection((HOST, 443), timeout=timeout) as sock:
            with ssl.create_default_context().wrap_socket(sock, server_hostname=HOST):
                result["tls"] = "ok"
    except (OSError, ssl.SSLError):
        result["tls"] = "failed"
        return result
    agent = os.getenv("SEC_USER_AGENT", "").strip()
    valid_agent = bool(agent and "@" in agent and "example.com" not in agent.lower())
    result["sec_user_agent_configured"] = valid_agent
    if not valid_agent:
        result["http"] = "skipped_missing_sec_user_agent"
        return result
    try:
        # GET is representative of the production client; read at most one byte
        # and never persist or log SEC response content.
        request = Request(URL, headers={"User-Agent": agent, "Accept": "application/json"})
        with urlopen(request, timeout=timeout) as response:
            response.read(1)
            result["http"] = str(response.status)
    except HTTPError as exc:
        result["http"] = str(exc.code)
    except (URLError, TimeoutError, OSError):
        result["http"] = "network_error"
    return result
