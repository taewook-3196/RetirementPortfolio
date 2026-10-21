"""Build auditable point-in-time PBR observations from dated prices and filings.

Each price uses only BPS disclosed on or before that price date. No fetching.
"""
from datetime import date
import math


def build_point_in_time_pbr(prices, filings, *, as_of, max_bps_age_days=550):
    """Prices: (date, price). Filings: (publication_date, BPS).

    Both inputs must use the same per-share currency and share basis; callers
    must verify corporate actions and historical filing revisions.
    """
    try:
        cutoff = date.fromisoformat(as_of)
    except (TypeError, ValueError):
        return {"status": "withheld", "reason": "분석 기준일이 유효하지 않습니다."}
    if cutoff > date.today():
        return {"status": "withheld", "reason": "미래 기준일은 허용하지 않습니다."}
    valid_filings = []
    for item in filings:
        try:
            day = date.fromisoformat(item[0])
            bps = float(item[1])
        except (TypeError, ValueError, OverflowError, IndexError):
            continue
        if day <= cutoff and math.isfinite(bps) and bps > 0:
            valid_filings.append((day, bps))
    valid_filings.sort()
    valid_prices = []
    for item in prices:
        try:
            day = date.fromisoformat(item[0])
            price = float(item[1])
        except (TypeError, ValueError, OverflowError, IndexError):
            continue
        if day <= cutoff and math.isfinite(price) and price > 0:
            valid_prices.append((day, price))
    valid_prices.sort()
    observations = []
    filing_index = 0
    latest_filing = None
    for day, price in valid_prices:
        while filing_index < len(valid_filings) and valid_filings[filing_index][0] <= day:
            latest_filing = valid_filings[filing_index]
            filing_index += 1
        if latest_filing is None or (day - latest_filing[0]).days > max_bps_age_days:
            continue
        observations.append((day.isoformat(), round(price / latest_filing[1], 6)))
    return {
        "status": "reference_only" if observations else "withheld",
        "observations": observations,
        "count": len(observations),
        "disclaimer": "공시일 기준 BPS만 적용했습니다. 수정공시·주식분할·주당 단위·통화 일치 여부는 별도 검증이 필요합니다.",
    }
