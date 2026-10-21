"""Parse SEC EDGAR companyfacts equity facts without forward-looking restatements.

This is an offline normalization step, not a live SEC API client.
"""
from datetime import date
import math

EQUITY_TAGS = (
    "StockholdersEquity",
    "CommonStockholdersEquity",
)


def parse_sec_equity_filings(companyfacts, *, as_of):
    """Return (filed_date, equity_usd) for unambiguous 10-Q/10-K instants.

    Multiple facts disclosed on the same day for different periods are not
    silently collapsed; the most recent reporting period is selected.
    """
    try:
        cutoff = date.fromisoformat(as_of)
        facts = companyfacts["facts"]["us-gaap"]
    except (TypeError, ValueError, KeyError):
        return {"status": "withheld", "reason": "SEC companyfacts 구조 또는 기준일이 유효하지 않습니다."}
    if cutoff > date.today():
        return {"status": "withheld", "reason": "미래 기준일은 허용하지 않습니다."}
    records = []
    for tag in EQUITY_TAGS:
        for fact in facts.get(tag, {}).get("units", {}).get("USD", []):
            try:
                filed = date.fromisoformat(fact["filed"])
                period = date.fromisoformat(fact["end"])
                value = float(fact["val"])
                form = fact["form"]
                accession = fact["accn"]
            except (TypeError, ValueError, OverflowError, KeyError):
                continue
            if form not in ("10-K", "10-Q") or not accession or filed > cutoff:
                continue
            if period > filed or not math.isfinite(value) or value <= 0:
                continue
            records.append((filed, period, value, tag, accession))
    if not records:
        return {"status": "withheld", "reason": "유효한 SEC 자기자본 공시를 찾지 못했습니다.", "filings": []}
    by_filing = {}
    for filed, period, value, tag, accession in records:
        key = (filed, accession)
        candidate = (period, tag == "CommonStockholdersEquity", value)
        if key not in by_filing or candidate[:2] > by_filing[key][:2]:
            by_filing[key] = candidate
    output = sorted(
        ({"filed": filed.isoformat(), "accession": accession,
          "period_end": period.isoformat(), "equity_usd": value}
         for (filed, accession), (period, _, value) in by_filing.items()),
        key=lambda x: (x["filed"], x["accession"]),
    )
    return {
        "status": "reference_only",
        "filings": output,
        "note": "자기자본 금액만 추출했습니다. 보통주 주식수, 수정공시, 지배기업 귀속분 및 주식분할 검증 전에는 BPS/PBR을 계산하지 않습니다.",
    }
