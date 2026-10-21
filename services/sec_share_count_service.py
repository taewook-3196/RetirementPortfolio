"""Extract filing-dated common share counts from SEC companyfacts.

Share-count facts are not automatically comparable with historic adjusted prices.
"""
from datetime import date
import math

SHARE_TAGS = (
    "CommonStockSharesOutstanding",
    "EntityCommonStockSharesOutstanding",
)


def parse_sec_share_filings(companyfacts, *, as_of):
    """Return disclosed share count observations, preserving accession and period."""
    try:
        cutoff = date.fromisoformat(as_of)
        namespaces = companyfacts["facts"]
    except (TypeError, ValueError, KeyError):
        return {"status": "withheld", "reason": "SEC companyfacts 구조 또는 기준일이 유효하지 않습니다.", "filings": []}
    if cutoff > date.today():
        return {"status": "withheld", "reason": "미래 기준일은 허용하지 않습니다.", "filings": []}
    candidates = []
    for namespace, tag in (("us-gaap", SHARE_TAGS[0]), ("dei", SHARE_TAGS[1])):
        entries = namespaces.get(namespace, {}).get(tag, {}).get("units", {}).get("shares", [])
        for fact in entries:
            try:
                filed = date.fromisoformat(fact["filed"])
                period = date.fromisoformat(fact["end"])
                value = float(fact["val"])
                form = fact["form"]
                accession = fact["accn"]
            except (TypeError, ValueError, OverflowError, KeyError):
                continue
            if filed > cutoff or period > filed or form not in ("10-K", "10-Q"):
                continue
            if not accession or not math.isfinite(value) or value <= 0:
                continue
            candidates.append((filed, period, accession, namespace, tag, value))
    filings = [
        {"filed": filed.isoformat(), "period_end": period.isoformat(),
         "accession": accession, "taxonomy": namespace, "tag": tag, "shares": value}
        for filed, period, accession, namespace, tag, value in sorted(set(candidates))
    ]
    return {
        "status": "reference_only" if filings else "withheld",
        "filings": filings,
        "note": "보통주 주식수의 공시 시점만 정규화했습니다. 자기자본과 보고기준일·주식 종류·분할 조정이 일치하지 않으면 BPS 계산 금지.",
    }


def match_equity_and_shares(equity_filings, share_filings):
    """Pair only same-accession and same-period observations; no interpolation."""
    shares = {}
    for row in share_filings:
        shares.setdefault((row["accession"], row["period_end"]), []).append(row)
    matches = []
    for equity in equity_filings:
        options = shares.get((equity["accession"], equity["period_end"]), [])
        if len(options) != 1 or equity["equity_usd"] <= 0:
            continue
        share = options[0]
        if share["shares"] <= 0:
            continue
        matches.append({
            "filed": max(equity["filed"], share["filed"]),
            "period_end": equity["period_end"],
            "accession": equity["accession"],
            "bps_unadjusted_usd": round(equity["equity_usd"] / share["shares"], 8),
            "status": "requires_corporate_action_validation",
        })
    return matches
