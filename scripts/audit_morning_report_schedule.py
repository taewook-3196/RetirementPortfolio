"""Read-only GitHub Actions schedule audit; never triggers Kakao delivery.

Example: python -m scripts.audit_morning_report_schedule --date 2026-10-13
Requires GITHUB_TOKEN with Actions read permission (or public API access).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request
import urllib.parse
from zoneinfo import ZoneInfo

SEOUL = ZoneInfo("Asia/Seoul")
WORKFLOW = "morning_report.yml"


def expected_slots(day: dt.date) -> tuple[str, ...]:
    return ("05:35", "07:10", "09:00") if day.weekday() in (1, 2, 3, 4, 5) else ()


def audit_runs(day: dt.date, runs: list[dict]) -> dict:
    scheduled = []
    manual = []
    for run in runs:
        try:
            stamp = dt.datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
            local_date = stamp.astimezone(SEOUL).date()
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        if local_date != day:
            continue
        event = run.get("event")
        item = {"id": run.get("id"), "status": run.get("status"), "conclusion": run.get("conclusion")}
        if event == "schedule":
            scheduled.append(item)
        elif event == "workflow_dispatch":
            manual.append(item)
    expected = expected_slots(day)
    if not expected:
        diagnosis = "not_scheduled_day"
    elif not scheduled:
        diagnosis = "no_scheduled_runs"
    elif any(run["conclusion"] == "success" for run in scheduled):
        diagnosis = "scheduled_run_succeeded_delivery_unverified"
    elif any(run["status"] != "completed" for run in scheduled):
        diagnosis = "scheduled_run_in_progress"
    else:
        diagnosis = "scheduled_runs_completed_without_success"
    return {
        "date_kst": day.isoformat(),
        "diagnosis": diagnosis,
        "expected_slots_kst": list(expected),
        "scheduled_runs": scheduled,
        "manual_runs": manual,
        "schedule_missing": bool(expected) and not scheduled,
        "note": "Workflow-run metadata only; successful runs do not prove Kakao delivery.",
    }


def fetch_runs(repository: str, token: str | None = None, day: dt.date | None = None) -> list[dict]:
    parts = repository.split("/")
    if len(parts) != 2 or not all(parts) or any(not part.replace("-", "").replace("_", "").replace(".", "").isalnum() for part in parts):
        raise ValueError("repository must be owner/name")
    params = {"per_page": "100"}
    if day is not None:
        start = dt.datetime.combine(day, dt.time.min, SEOUL).astimezone(dt.timezone.utc)
        end = start + dt.timedelta(days=1)
        params["created"] = start.strftime("%Y-%m-%dT%H:%M:%SZ") + ".." + end.strftime("%Y-%m-%dT%H:%M:%SZ")
    url = "https://api.github.com/repos/" + repository + "/actions/workflows/" + WORKFLOW + "/runs?" + urllib.parse.urlencode(params)
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "RetirementPortfolio-schedule-audit"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=20) as response:
        data = json.load(response)
    if data.get("total_count", 0) > len(data["workflow_runs"]):
        raise ValueError("workflow run query exceeded single-page audit capacity")
    return data["workflow_runs"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=dt.date.fromisoformat, default=dt.datetime.now(SEOUL).date())
    parser.add_argument("--repository", default=os.getenv("GITHUB_REPOSITORY", "taewook-3196/RetirementPortfolio"))
    args = parser.parse_args(argv)
    try:
        result = audit_runs(args.date, fetch_runs(args.repository, os.getenv("GITHUB_TOKEN"), args.date))
    except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as exc:
        print("Schedule audit unavailable: " + type(exc).__name__, file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["schedule_missing"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
