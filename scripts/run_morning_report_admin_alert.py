"""Explicitly gated administrator notification CLI.

Runs the read-only audit and prints an aggregate outcome. Webhook sending
requires BOTH --send and an administrator-provided HTTPS webhook URL.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path

from scripts.audit_morning_report_schedule import SEOUL
from scripts.morning_report_admin_alert import classify_admin_alert
from scripts.morning_report_alert_runner import process_admin_alert
from scripts.morning_report_alert_webhook import send_admin_webhook
from scripts.run_morning_report_delivery_audit import run_audit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--send", action="store_true", help="explicitly allow administrator webhook delivery")
    parser.add_argument("--date", type=dt.date.fromisoformat)
    parser.add_argument("--repository", default=os.getenv("GITHUB_REPOSITORY", "taewook-3196/RetirementPortfolio"))
    args = parser.parse_args(argv)
    day = args.date or dt.datetime.now(SEOUL).date()
    try:
        result = run_audit(day, dt.datetime.now(SEOUL), args.repository)
        alert = classify_admin_alert(result)
        if not args.send:
            print(json.dumps({"mode": "dry_run", "should_alert": alert["should_alert"]}))
            return 0
        url = os.getenv("MORNING_REPORT_ADMIN_WEBHOOK_URL")
        store = os.getenv("MORNING_REPORT_ALERT_STORE_DIR")
        if not url or not store:
            raise ValueError("webhook URL and durable alert store are required")
        status = process_admin_alert(
            result,
            store_directory=Path(store),
            send=lambda message: send_admin_webhook(message, url=url),
        )
        print(json.dumps({"mode": "send", "status": status}))
        return 0
    except Exception as exc:
        # Never print exception messages that might contain credentials.
        print(json.dumps({"status": "unavailable", "error_type": type(exc).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
