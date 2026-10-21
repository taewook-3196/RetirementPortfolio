"""Compare SEC companyfacts pilot results without implying PBR readiness."""


def summarize_sec_pilot_reports(reports):
    items = []
    for report in reports:
        if not isinstance(report, dict) or "coverage" not in report:
            continue
        coverage = report.get("coverage") or {}
        audit = report.get("match_audit") or {}
        equity_count = int(report.get("equity_filings") or 0)
        matched_count = int(report.get("strictly_matched_filings") or 0)
        items.append({
            "cik": report.get("cik"),
            "company": report.get("company"),
            "equity_filings": equity_count,
            "strict_matches": matched_count,
            "match_rate_pct": round(100 * matched_count / equity_count, 1) if equity_count else None,
            "distinct_quarters": coverage.get("distinct_quarters", 0),
            "span_years": coverage.get("span_years", 0),
            "coverage_status": coverage.get("status", "withheld"),
            "mismatch_reasons": audit.get("reasons", {}),
            "investment_ready": False,
        })
    return {
        "status": "diagnostic_only",
        "company_count": len(items),
        "coverage_sufficient_count": sum(
            item["coverage_status"] == "pilot_coverage_sufficient" for item in items
        ),
        "investment_ready_count": 0,
        "companies": items,
        "note": "공시자료 충족률은 주가·기업행동·원본 출처 검증을 대체하지 않습니다.",
    }
