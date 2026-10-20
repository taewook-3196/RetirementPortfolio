"""Gate PBR bands on auditable source, accounting and industry metadata."""
from datetime import date
import math

from services.pbr_band_service import calculate_pbr_band

UNSUITABLE_INDUSTRIES = {"software", "internet_platforms", "biotechnology"}
FINANCIAL_INDUSTRIES = {"banks", "insurance"}

def evaluate_pbr_band(observations, current_pbr, *, source, as_of, industry,
                      current_bps, current_roe, reporting_currency,
                      source_verified=False, accounting_consistent=False):
    """Return a reference band only when source and book-value quality are verified."""
    if not source_verified or not source or not str(source).strip():
        return {"status": "withheld", "reason": "재무정보 출처가 검증되지 않았습니다."}
    if not accounting_consistent:
        return {"status": "withheld", "reason": "과거 BPS와 회계 기준의 비교 가능성이 검증되지 않았습니다."}
    if not reporting_currency or not str(reporting_currency).strip():
        return {"status": "withheld", "reason": "재무제표 통화 정보가 없습니다."}
    if industry in UNSUITABLE_INDUSTRIES:
        return {"status": "withheld", "reason": "무형자산 비중 등으로 PBR 비교 적합성 검토가 필요한 산업입니다."}
    try:
        bps = float(current_bps)
        roe = float(current_roe)
    except (TypeError, ValueError, OverflowError):
        return {"status": "withheld", "reason": "BPS 또는 ROE 데이터가 없습니다."}
    if not all(math.isfinite(x) for x in (bps, roe)) or bps <= 0:
        return {"status": "withheld", "reason": "BPS 또는 ROE가 유효하지 않습니다."}
    if industry in FINANCIAL_INDUSTRIES:
        return {"status": "withheld", "reason": "금융업은 자본규제·자산건전성 등을 포함한 별도 검증 전까지 보류합니다."}
    try:
        cutoff = date.fromisoformat(as_of)
    except (TypeError, ValueError):
        return {"status": "withheld", "reason": "재무정보 기준일이 유효하지 않습니다."}
    if cutoff > date.today():
        return {"status": "withheld", "reason": "미래 재무정보 기준일은 허용하지 않습니다."}
    result = calculate_pbr_band(observations, current_pbr, as_of=cutoff)
    if result["status"] == "reference_only":
        result["data_quality"] = {
            "source": str(source), "as_of": cutoff.isoformat(),
            "industry": industry, "reporting_currency": str(reporting_currency),
            "current_bps": bps, "current_roe": roe,
            "source_verified": True, "accounting_consistent": True,
        }
    return result
