"""Validation for future opening-account snapshots.

Pure validation only: no persistence, DB schema change or balance calculation.
"""
from datetime import date
from decimal import Decimal, InvalidOperation


def validate_opening_snapshot(opening_date, cash_amount, currency, holdings=None):
    errors = []
    if not isinstance(opening_date, date) or isinstance(opening_date, __import__("datetime").datetime):
        errors.append("계좌 시작 기준일이 필요합니다.")
    elif opening_date > date.today():
        errors.append("계좌 시작 기준일은 미래일 수 없습니다.")

    normalized_currency = str(currency or "").strip().upper()
    if normalized_currency not in {"KRW", "USD"}:
        errors.append("지원하는 계좌 통화는 KRW 또는 USD입니다.")

    def parse_nonnegative(value, label):
        try:
            number = Decimal(str(value))
            if not number.is_finite() or number < 0:
                raise InvalidOperation()
            return number
        except (InvalidOperation, ValueError, TypeError):
            errors.append(label + "은 0 이상의 유효한 숫자여야 합니다.")
            return None

    cash = parse_nonnegative(cash_amount, "시작 현금잔고")
    clean_holdings = []
    seen = set()
    for holding in holdings or []:
        if not isinstance(holding, dict):
            errors.append("시작 보유종목 정보가 올바르지 않습니다.")
            continue
        ticker = str(holding.get("ticker") or "").strip().upper()
        if not ticker or ticker in seen:
            errors.append("시작 보유종목 코드는 비어 있거나 중복될 수 없습니다.")
            continue
        seen.add(ticker)
        quantity = parse_nonnegative(holding.get("quantity"), ticker + " 수량")
        value = parse_nonnegative(holding.get("market_value"), ticker + " 평가금액")
        if quantity is not None and quantity == 0 and value not in (None, Decimal(0)):
            errors.append(ticker + " 수량이 0이면 평가금액도 0이어야 합니다.")
        clean_holdings.append({
            "ticker": ticker,
            "quantity": quantity,
            "market_value": value,
        })
    return {
        "valid": not errors,
        "errors": errors,
        "opening_date": opening_date,
        "currency": normalized_currency,
        "cash_amount": cash,
        "holdings": clean_holdings,
    }
