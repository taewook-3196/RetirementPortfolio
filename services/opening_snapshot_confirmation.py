"""Conservative pre-confirmation checks for an account opening snapshot.

Read-only, no DB writes. Warnings require explicit user reconciliation; this
module deliberately does not infer historical positions or returns.
"""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from services.opening_snapshot_validation import validate_opening_snapshot


def check_opening_snapshot_confirmation(snapshot, transactions=None, cash_flows=None, dividends=None, account_currency=None):
    blockers = []
    warnings = []
    if not snapshot:
        return {"can_confirm": False, "blockers": [{"code": "SNAPSHOT_MISSING", "message": "저장된 시작 자산 초안이 없습니다."}], "warnings": []}
    if account_currency is not None and str(snapshot.get("currency") or "").strip().upper() != str(account_currency or "").strip().upper():
        blockers.append({"code": "ACCOUNT_CURRENCY_MISMATCH", "message": "시작 자산 통화가 계좌 기준 통화와 일치하지 않습니다."})
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
    # Reconstruct quantities from the opening state only when event dates and
    # transaction fields are usable; this is a consistency check, not a balance.
    quantities = {}
    for holding in snapshot.get("holdings", []):
        if not isinstance(holding, dict):
            continue
        ticker = str(holding.get("ticker") or "").strip().upper()
        try:
            quantity = Decimal(str(holding.get("quantity")))
        except (InvalidOperation, TypeError, ValueError):
            continue
        if ticker and quantity.is_finite() and quantity >= 0:
            quantities[ticker] = quantity
    def trade_sort_key(event):
        event_date = getattr(event, "transaction_date", None)
        if isinstance(event_date, datetime):
            event_date = event_date.date()
        if not isinstance(event_date, date):
            event_date = date.min
        # Preserve original input order for same-day trades: a database ID
        # cannot establish execution order for trades recorded on one date.
        return event_date

    # A date-only ledger cannot prove intraday execution order. When a ticker
    # has both BUY and SELL on one date, flag the ambiguity for manual review.
    same_day_sides = {}
    for trade in trades:
        trade_date = getattr(trade, "transaction_date", None)
        if isinstance(trade_date, datetime):
            trade_date = trade_date.date()
        if not opening or not isinstance(trade_date, date) or trade_date <= opening:
            continue
        ticker = str(getattr(trade, "ticker", "") or "").strip().upper()
        side = str(getattr(trade, "transaction_type", "") or "").strip().upper()
        if ticker and side in {"BUY", "SELL"}:
            same_day_sides.setdefault((trade_date, ticker), set()).add(side)
    ambiguous = sorted(ticker for (_, ticker), sides in same_day_sides.items() if sides == {"BUY", "SELL"})
    if ambiguous:
        warnings.append({
            "code": "SAME_DAY_TRADE_ORDER_UNKNOWN",
            "message": "같은 날짜에 매수와 매도가 함께 기록된 종목이 있습니다. 거래 시각을 알 수 없어 순서와 수량을 확인해야 합니다.",
            "tickers": sorted(set(ambiguous)),
        })

    for trade in sorted(trades, key=trade_sort_key):
        trade_date = getattr(trade, "transaction_date", None)
        if isinstance(trade_date, datetime):
            trade_date = trade_date.date()
        if not opening or not isinstance(trade_date, date) or trade_date <= opening:
            continue
        ticker = str(getattr(trade, "ticker", "") or "").strip().upper()
        side = str(getattr(trade, "transaction_type", "") or "").strip().upper()
        try:
            amount = Decimal(str(getattr(trade, "quantity", None)))
        except (InvalidOperation, TypeError, ValueError):
            amount = Decimal("-1")
        if not ticker or side not in {"BUY", "SELL"} or not amount.is_finite() or amount <= 0:
            blockers.append({"code": "INVALID_TRADE_QUANTITY", "message": "거래내역에 종목, 매수/매도 구분 또는 수량 오류가 있습니다."})
            continue
        current = quantities.get(ticker, Decimal("0"))
        if side == "SELL" and current < amount:
            blockers.append({"code": "NEGATIVE_RECONCILED_POSITION", "message": ticker + " 종목의 매도 수량이 시작 보유수량과 이후 매수 수량을 초과합니다.", "tickers": [ticker]})
        quantities[ticker] = current + (amount if side == "BUY" else -amount)
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
