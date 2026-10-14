"""Opt-in administrator webhook transport. No network call occurs on import."""
from __future__ import annotations

import ipaddress
import json
import socket
import urllib.error
import urllib.parse
import urllib.request


def send_admin_webhook(message: str, *, url: str, timeout: int = 10) -> None:
    """Send a small JSON alert to an explicitly configured HTTPS endpoint.

    This is an adapter, not an enabled notification service. Callers must
    configure an approved endpoint and protect its credentials.
    """
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("webhook must be an HTTPS URL without userinfo or fragment")
    if timeout <= 0 or timeout > 30:
        raise ValueError("timeout must be between 1 and 30 seconds")
    # Block literal loopback/private IP targets. A production transport
    # should also enforce network-level egress restrictions against SSRF.
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise ValueError("webhook cannot target a non-public IP")
    payload = json.dumps({"text": message}, ensure_ascii=False).encode("utf-8")
    if len(payload) > 4096:
        raise ValueError("alert message exceeds webhook size limit")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "RetirementPortfolio-watchdog"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError("webhook rejected alert")
    except (urllib.error.URLError, TimeoutError) as exc:
        # Never include URL or response body in exception text.
        raise RuntimeError("webhook delivery status unknown") from None
