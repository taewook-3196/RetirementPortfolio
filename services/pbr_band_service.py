"""Historical PBR band calculation. No remote fetches or trade recommendations."""
from datetime import date
import math
import statistics

def calculate_pbr_band(observations, current_pbr, as_of=None):
    """Compute reference-only percentiles from (ISO date, PBR) observations."""
    as_of = as_of or date.today()
    try:
        current = float(current_pbr)
    except (TypeError, ValueError, OverflowError):
        current = float("nan")
    if not math.isfinite(current) or current <= 0:
        return {"status": "withheld", "reason": "현재 PBR이 유효하지 않습니다."}
    by_date = {}
    for entry in observations:
        try:
            day = date.fromisoformat(entry[0])
            value = float(entry[1])
        except (TypeError, ValueError, OverflowError, IndexError):
            continue
        if day <= as_of and math.isfinite(value) and value > 0:
            by_date[day] = value
    ordered = sorted(by_date.items())
    if len(ordered) < 20:
        return {"status": "withheld", "reason": "유효한 과거 PBR 관측치가 20개 미만입니다.", "valid_count": len(ordered)}
    if (ordered[-1][0] - ordered[0][0]).days < 365 * 5:
        return {"status": "withheld", "reason": "PBR 관측 기간이 5년 미만입니다.", "valid_count": len(ordered)}
    values = sorted(value for _, value in ordered)
    def percentile(p):
        index = (len(values) - 1) * p
        low = int(index)
        high = min(low + 1, len(values) - 1)
        return round(values[low] + (values[high] - values[low]) * (index - low), 4)
    rank = 100 * (sum(v < current for v in values) + .5 * sum(v == current for v in values)) / len(values)
    return {
        "status": "reference_only",
        "current_pbr": round(current, 4),
        "historical_percentile": round(rank, 1),
        "band": {"p10": percentile(.1), "p25": percentile(.25), "median": round(statistics.median(values), 4), "p75": percentile(.75), "p90": percentile(.9)},
        "valid_count": len(values),
        "first_date": ordered[0][0].isoformat(),
        "last_date": ordered[-1][0].isoformat(),
        "disclaimer": "과거 PBR 분포 참고치이며 저평가·매수 추천이 아닙니다. ROE, BPS, 회계 변경과 산업 적합성을 별도 검증해야 합니다.",
    }
