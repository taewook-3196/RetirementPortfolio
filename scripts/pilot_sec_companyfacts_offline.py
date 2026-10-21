"""Run SEC companyfacts coverage audit on locally downloaded official JSON.

Usage:
  python -m scripts.pilot_sec_companyfacts_offline --file CIK0000320193.json
No API key or SEC User-Agent is needed for local file analysis.
"""
import argparse
import json
from pathlib import Path
import time

from scripts.pilot_sec_companyfacts import analyze_companyfacts
from services.sec_pilot_batch_summary import summarize_sec_pilot_reports


def audit_local_companyfacts(path, *, as_of):
    source = Path(path)
    if not source.is_file():
        raise ValueError("JSON 파일을 찾을 수 없습니다.")
    if source.stat().st_size > 12_000_000:
        raise ValueError("12MB를 초과한 JSON 파일은 처리하지 않습니다.")
    with source.open("r", encoding="utf-8") as stream:
        payload = json.load(stream)
    if not isinstance(payload, dict) or not isinstance(payload.get("facts"), dict):
        raise ValueError("SEC companyfacts 형식이 아닙니다.")
    cik = str(payload.get("cik", ""))
    if not cik.isdigit() or len(cik) > 10:
        raise ValueError("SEC companyfacts CIK가 유효하지 않습니다.")
    result = analyze_companyfacts(payload, cik=cik, as_of=as_of)
    result["source"] = "user_supplied_sec_json"
    result["source_verified"] = False
    return result


def main():
    parser = argparse.ArgumentParser(description="다운로드한 SEC companyfacts JSON 검증")
    parser.add_argument("--file", action="append", required=True, help="SEC companyfacts JSON 파일, 최대 3개")
    parser.add_argument("--as-of", default=time.strftime("%Y-%m-%d"))
    args = parser.parse_args()
    if len(args.file) > 3:
        parser.error("한 번에 최대 3개 파일만 검사합니다.")
    successful_reports = []
    for path in args.file:
        try:
            report = audit_local_companyfacts(path, as_of=args.as_of)
            successful_reports.append(report)
            print(json.dumps(report, ensure_ascii=False))
        except (ValueError, OSError, json.JSONDecodeError, TypeError) as exc:
            print(json.dumps({"file": path, "status": "error", "error_type": type(exc).__name__}, ensure_ascii=False))
    print(json.dumps({"batch_summary": summarize_sec_pilot_reports(successful_reports)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
