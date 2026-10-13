"""Side-effect-controlled administrator alert orchestration.

This module has no configured transport and cannot send messages by itself.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from scripts.morning_report_admin_alert import classify_admin_alert
from scripts.morning_report_admin_message import format_admin_alert
from scripts.morning_report_alert_store import claim_alert_with_expiry


def process_admin_alert(
    audit: dict,
    *,
    store_directory: str | Path,
    send: Callable[[str], None],
) -> str:
    """Return skipped/duplicate/sent; propagate unknown send failures.

    The caller must explicitly provide a trusted synchronous transport.
    If the transport raises, its delivery state may be unknown, so the claim
    is retained to avoid a potentially duplicated notification.
    """
    alert = classify_admin_alert(audit)
    if not alert["should_alert"]:
        return "skipped"
    key = alert["dedup_key"]
    if not claim_alert_with_expiry(key, store_directory):
        return "duplicate"
    message = format_admin_alert(audit)
    if message is None:
        # Defensive: keep the claim; this mismatch must be investigated.
        raise RuntimeError("alert classification mismatch")
    send(message)
    return "sent"
