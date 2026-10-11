"""SEC EDGAR companyfacts reader for US GAAP trailing financials.

Public, unauthenticated source; no forecast PE or analyst growth estimates.
Requests are bounded and require an identifying User-Agent configured by the operator.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import time
import threading
from urllib.request import Request, urlopen

SEC_BASE = "https://data.sec.gov"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
CACHE = {}
TTL = 86400
SEC_REQUEST_LOCK = threading.Lock()
_last_sec_request = 0.0


def _get_json(url):
    agent = os.getenv("SEC_USER_AGENT", "").strip()
    if not agent or "@" not in agent:
        raise RuntimeError("SEC_USER_AGENT identifying contact is not configured")
    request = Request(url, headers={
        "User-Agent": agent,
        "Accept": "application/json",
        "Accept-Encoding": "identity",
    })
    global _last_sec_request
    # SEC requests are globally serialized and throttled within this process.
    with SEC_REQUEST_LOCK:
        wait = 0.2 - (time.monotonic() - _last_sec_request)
        if wait > 0:
            time.sleep(wait)
        _last_sec_request = time.monotonic()
        with urlopen(request, timeout=12) as response:
            return json.load(response)


def _cached(key, fetch):
    cached = CACHE.get(key)
    if cached and time.monotonic() - cached[0] < TTL:
        return cached[1]
    value = fetch()
    CACHE[key] = (time.monotonic(), value)
    return value


def _cik_for_ticker(ticker):
    tickers = _cached("tickers", lambda: _get_json(TICKERS_URL))
    for entry in tickers.values():
        if entry.get("ticker", "").upper().replace("-", ".") == ticker.upper().replace("-", "."):
            return int(entry["cik_str"])
    raise ValueError("Ticker is not in SEC ticker map")


def _annual_facts(facts, tags):
    gaap = facts.get("facts", {}).get("us-gaap", {})
    candidates = []
    for tag in tags:
        units = gaap.get(tag, {}).get("units", {}).get("USD", [])
        candidates.extend(
            row for row in units
            if row.get("form") in ("10-K", "10-K/A")
            and row.get("fy") and row.get("fp") == "FY"
            and row.get("start") and row.get("end")
            and 330 <= (datetime.fromisoformat(row["end"]) - datetime.fromisoformat(row["start"])).days <= 380
        )
    if candidates:
        best = max(candidates, key=lambda row: (row["end"], row.get("filed", "")))
        return float(best["val"]), best["end"]
    return None, None


def fetch_sec_fundamentals(ticker):
    """Returns verified annual sales/profit figures only, never invented ratios."""
    if not ticker or ticker.endswith((".KS", ".KQ")):
        raise ValueError("SEC reader supports US tickers only")
    cik = _cik_for_ticker(ticker)
    facts = _cached(("facts", cik), lambda: _get_json(f"{SEC_BASE}/api/xbrl/companyfacts/CIK{cik:010d}.json"))
    revenue, revenue_date = _annual_facts(facts, (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues", "SalesRevenueNet",
    ))
    income, income_date = _annual_facts(facts, ("NetIncomeLoss",))
    if revenue is None or income is None or revenue_date != income_date or revenue <= 0:
        raise ValueError("Comparable annual sales and net income are unavailable")
    return {
        "shortName": facts.get("entityName", ticker),
        "profitMargins": income / revenue,
        "source": "SEC EDGAR companyfacts",
        "financials_as_of": revenue_date,
    }
