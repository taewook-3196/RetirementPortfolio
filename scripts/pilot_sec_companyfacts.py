"""Manual, read-only SEC companyfacts connectivity and coverage pilot.

Usage:
  SEC_USER_AGENT='RetirementPortfolio Research contact@example.com' \
    python -m scripts.pilot_sec_companyfacts --cik 0000320193
Requires a real operator contact in User-Agent. Never run as an unthrottled job.
"""
import argparse
import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from services.sec_companyfacts_service import parse_sec_equity_filings
from services.sec_share_count_service import parse_sec_share_filings, match_equity_and_shares
from services.pbr_pilot_coverage_service import assess_pbr_pilot_coverage

SEC_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"


def fetch_sec_companyfacts(cik, *, user_agent, timeout=20):
    if not isinstance(cik, str) or not cik.isdigit() or len(cik) > 10:
        raise ValueError("CIK는 10자리 이하의 숫자여야 합니다.")
    if not user_agent or "@" not in user_agent or "example.com" in user_agent.lower():
        raise ValueError("SEC_USER_AGENT에 실제 운영자 이름과 연락처 이메일을 지정하세요.")
    request = Request(
        SEC_COMPANYFACTS_URL.format(cik=cik.zfill(10)),
        headers={"User-Agent": user_agent, "Accept": "application/json"},
    )
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError("SEC API returned non-200 status")
        payload = response.read(12_000_001)
        if len(payload) > 12_000_000:
            raise ValueError("SEC 응답이 허용된 12MB를 초과했습니다.")
        return json.loads(payload)


def run_pilot(cik, *, user_agent, as_of):
    payload = fetch_sec_companyfacts(cik, user_agent=user_agent)
    equity = parse_sec_equity_filings(payload, as_of=as_of)
    shares = parse_sec_share_filings(payload, as_of=as_of)
    matched = match_equity_and_shares(equity.get("filings", []), shares.get("filings", []))
    coverage = assess_pbr_pilot_coverage(matched, as_of=as_of)
    return {
        "cik": cik.zfill(10),
        "company": payload.get("entityName"),
        "equity_filings": len(equity.get("filings", [])),
        "share_filings": len(shares.get("filings", [])),
        "strictly_matched_filings": len(matched),
        "coverage": coverage,
        "note": "SEC 무료 응답 기반 탐색적 진단. 실제 투자용 PBR 검증이나 가격·기업행동 검증 완료를 뜻하지 않습니다.",
    }


def main():
    parser = argparse.ArgumentParser(description="SEC 무료 companyfacts 진단")
    parser.add_argument("--cik", action="append", required=True, help="CIK, 최대 3개")
    parser.add_argument("--as-of", default=time.strftime("%Y-%m-%d"))
    args = parser.parse_args()
    if len(args.cik) > 3:
        parser.error("한 번에 최대 3개 기업만 검사합니다.")
    agent = os.getenv("SEC_USER_AGENT", "")
    if not agent or "@" not in agent or "example.com" in agent.lower():
        parser.error("SEC_USER_AGENT에 실제 운영자 이름과 이메일이 필요합니다.")
    for i, cik in enumerate(args.cik):
        if i:
            time.sleep(1)
        try:
            print(json.dumps(run_pilot(cik, user_agent=agent, as_of=args.as_of), ensure_ascii=False))
        except (HTTPError, URLError, ValueError, RuntimeError, TimeoutError) as exc:
            print(json.dumps({"cik": cik, "status": "error", "error_type": type(exc).__name__}, ensure_ascii=False))


if __name__ == "__main__":
    main()
