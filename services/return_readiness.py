"""Read-only checks for historical account-return calculation readiness.

This module does not calculate or estimate returns and does not modify data.
"""
from datetime import date


def diagnose_return_readiness(account, cash_flows, transactions, dividends):
    """Return conservative blockers and data counts without exposing transactions."""
    flows = list(cash_flows or [])
    trades = list(transactions or [])
    payouts = list(dividends or [])
    warnings = [
        {
            "code": "OPENING_DATE_MISSING",
            "message": "시작 현금잔고의 기준일이 별도로 저장되지 않았습니다.",
        },
    ]
    if trades:
        warnings.append({
            "code": "OPENING_HOLDINGS_UNVERIFIED",
            "message": "계좌 시작 시점의 기존 보유종목과 이후 거래의 구분을 확인해야 합니다.",
        })
    currency = str(getattr(account, "currency", "KRW") or "KRW").upper()
    other_currencies = {
        str(getattr(flow, "currency", currency) or currency).upper()
        for flow in flows
    }
    other_currencies.update(
        str(getattr(payout, "currency", currency) or currency).upper()
        for payout in payouts
    )
    if any(value != currency for value in other_currencies):
        warnings.append({
            "code": "HISTORICAL_FX_UNVERIFIED",
            "message": "다른 통화의 입출금 또는 배당에 대한 거래 당시 환율을 검증해야 합니다.",
        })
    dates = [
        getattr(flow, "flow_date", None) for flow in flows
    ] + [
        getattr(trade, "transaction_date", None) for trade in trades
    ] + [
        getattr(payout, "dividend_date", None) for payout in payouts
    ]
    if any(not isinstance(value, date) for value in dates):
        warnings.append({
            "code": "EVENT_DATE_MISSING",
            "message": "일부 거래·입출금·배당의 날짜가 유효하지 않습니다.",
        })
    warnings.append({
        "code": "VALUATION_HISTORY_UNVERIFIED",
        "message": "현금흐름 시점의 과거 평가금액·가격·환율 자료가 검증되지 않았습니다.",
    })
    return {
        "ready_for_xirr": False,
        "ready_for_twr": False,
        "warnings": warnings,
        "counts": {
            "cash_flows": len(flows),
            "transactions": len(trades),
            "dividends": len(payouts),
        },
    }
