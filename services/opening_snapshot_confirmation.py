"""Conservative pre-confirmation checks for an account opening snapshot.

Read-only, no DB writes. Warnings require explicit user reconciliation; this
module deliberately does not infer historical positions or returns.
"""
from datetime import date, datetime

from services.opening_snapshot_validation import validate_opening_snapshot


def check_opening_snapshot_confirmation(snapshot, transactions=None, cash_flows=None, dividends=None):
    blockers = []
    warnings = []
    if not snapshot:
        return {"can_confirm": False, "blockers": [{"code": "SNAPSHOT_MISSING", "message": "저장된 시작 자산 초안이 없습니다."}], "warnings": []}
    if snapshot.get("status") != "draft":
        blockers.append({"code": "NOT_DRAFT", "message": "확정 가능한 초안 상태가 아닙니다."})
    try:
        opening = date.fromisoformat(snapshot["opening_date"])
    except (TypeError, ValueError, KeyError):
        opening = None
        blockers.append({"code": "INVALID_OPENING_DATE", "message": "시작 기준일이 올바르지 않습니다."})
    if opening and opening > date.today():
        blockers.append({"code": "FUTURE_OPENING_DATE", "message": "시작 기준일이 미래입니다."})
    if opening is not None:
        validated = validate_opening_snapshot(
            opening,
            snapshot.get("cash_amount"),
            snapshot.get("currency"),
            snapshot.get("holdings"),
        )
        if not validated["valid"]:
            blockers.append({
                "code": "INVALID_SNAPSHOT_VALUES",
                "message": "저장된 시작 자산 데이터가 유효하지 않습니다: " + "; ".join(validated["errors"]),
            })
    trades = list(transactions or [])
    flows = list(cash_flows or [])
    payouts = list(dividends or [])
    for kind, events, attribute in (
        ("거래", trades, "transaction_date"),
        ("입출금", flows, "flow_date"),
        ("배당", payouts, "dividend_date"),
    ):
        invalid = False
        before = False
        on_opening = False
        for event in events:
            event_date = getattr(event, attribute, None)
            if isinstance(event_date, datetime):
                event_date = event_date.date()
            if not isinstance(event_date, date):
                invalid = True
            elif opening and event_date < opening:
                before = True
            elif opening and event_date == opening:
                on_opening = True
        if invalid:
            blockers.append({"code": "INVALID_EVENT_DATE", "message": kind + " 내역에 날짜가 누락되거나 올바르지 않습니다."})
        if before:
            blockers.append({"code": "EVENT_BEFORE_OPENING", "message": "시작일 이전 " + kind + " 내역이 있습니다. 시작일 또는 기록을 확인해주세요."})
        if on_opening:
            warnings.append({"code": "EVENT_ON_OPENING_DATE", "message": "시작일 당일 " + kind + " 내역이 있습니다. 시작 자산에 이미 포함된 기록인지 확인해주세요."})
    opening_tickers = {str(item.get("ticker", "")).strip().upper() for item in snapshot.get("holdings", []) if isinstance(item, dict)}
    transaction_tickers = {str(getattr(trade, "ticker", "") or "").strip().upper() for trade in trades}
    overlap = sorted((opening_tickers & transaction_tickers) - {""})
    if overlap:
        warnings.append({"code": "OPENING_TRADE_OVERLAP", "message": "시작 보유종목과 거래기록에 공통 종목이 있습니다. 시작 수량이 거래기록에 이미 포함됐는지 확인해주세요.", "tickers": overlap})
    if trades and opening_tickers:
        warnings.append({"code": "HOLDINGS_RECONCILIATION_REQUIRED", "message": "시작 보유수량과 이후 거래를 대조해 현재 수량이 일치하는지 확인해야 합니다."})
    if flows:
        warnings.append({"code": "CASH_FLOW_RECONCILIATION_REQUIRED", "message": "시작 현금과 입출금 내역의 중복 반영 여부를 확인해야 합니다."})
    if payouts:
        warnings.append({"code": "DIVIDEND_RECONCILIATION_REQUIRED", "message": "시작일 이후 배당이 시작 현금에 이미 포함됐는지 확인해야 합니다."})
    return {"can_confirm": not blockers and not warnings, "blockers": blockers, "warnings": warnings}
