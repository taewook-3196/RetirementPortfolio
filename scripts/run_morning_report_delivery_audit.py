"""Read-only morning report audit CLI; never sends Kakao messages.

Run from an independently scheduled, authorized environment after 09:30 KST:
    python -m scripts.run_morning_report_delivery_audit

Exit 0: no missing markers; 1: missing markers or schedule; 2: check unavailable.
No user identifiers, secrets, or portfolio data are printed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error

from scripts.audit_morning_report_schedule import SEOUL, fetch_runs
from scripts.morning_report_delivery_watchdog import evaluate_delivery


def run_audit(day: dt.date, now: dt.datetime, repository: str) -> dict:
    # Import lazily so core tests don't require production database dependencies.
    from scripts.morning_report_delivery_reader import read_recipient_markers

    runs = fetch_runs(repository, os.getenv("GITHUB_TOKEN"))
    recipients = read_recipient_markers(day)
    return evaluate_delivery(day, now, runs, recipients)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=dt.date.fromisoformat)
    parser.add_argument("--repository", default=os.getenv("GITHUB_REPOSITORY", "taewook-3196/RetirementPortfolio"))
    args = parser.parse_args(argv)
    now = dt.datetime.now(SEOUL)
    day = args.date or now.date()
    try:
        result = run_audit(day, now, args.repository)
    except Exception as exc:
        # Keep credentials and user information out of logs.
        print(json.dumps({"status": "audit_unavailable", "error_type": type(exc).__name__}))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    if result["diagnosis"] in {"awaiting_cutoff", "historical_audit", "not_scheduled_day"}:
        return 0
    return 1 if result["missing_marker_count"] or result["scheduled_run_diagnosis"] == "no_scheduled_runs" else 0


if __name__ == "__main__":
    raise SystemExit(main())
