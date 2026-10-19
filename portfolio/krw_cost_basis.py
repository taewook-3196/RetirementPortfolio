"""Opt-in KRW moving-average cost basis. No portfolio or cash balance integration."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Iterable


def _decimal(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Invalid monetary value") from exc
    if not result.is_finite():
        raise ValueError("Non-finite monetary value")
    return result


@dataclass(frozen=True)
class KRWCostBasis:
    quantity: Decimal
    remaining_cost_krw: Decimal
    realized_pnl_krw: Decimal
    missing_settlement_count: int
    oversell_detected: bool

    @property
    def verified(self):
        return self.missing_settlement_count == 0 and not self.oversell_detected


def calculate_verified_krw_cost_basis(transactions: Iterable):
    """Replay chronologically; missing settlement invalidates verified PnL.

    Only explicitly supplied KRW settlement amounts are accepted. No FX
    interpolation or latest-rate fallback is performed. Settlement includes
    fees/taxes; BUY is cash paid and SELL is net cash received.
    """
    quantity = Decimal(0)
    cost = Decimal(0)
    realized = Decimal(0)
    missing = 0
    oversell = False
    for tx in sorted(transactions, key=lambda t: (t.transaction_date, t.id or 0)):
        kind = str(tx.transaction_type).upper()
        if kind not in ("BUY", "SELL"):
            continue
        qty = _decimal(tx.quantity)
        if qty <= 0:
            raise ValueError("Transaction quantity must be positive")
        amount = getattr(tx, "settlement_amount", None)
        currency = str(getattr(tx, "settlement_currency", "") or "").upper()
        if amount is None or currency != "KRW":
            missing += 1
            # Do not pretend that subsequent average cost is verified.
            if kind == "BUY":
                quantity += qty
            else:
                if qty > quantity:
                    oversell = True
                quantity = max(Decimal(0), quantity - qty)
            continue
        amount = _decimal(amount)
        if amount <= 0:
            raise ValueError("Settlement amount must be positive")
        if kind == "BUY":
            quantity += qty
            cost += amount
        else:
            if qty > quantity:
                oversell = True
                quantity = Decimal(0)
                cost = Decimal(0)
                continue
            allocated = cost * qty / quantity
            realized += amount - allocated
            cost -= allocated
            quantity -= qty
            if quantity == 0:
                cost = Decimal(0)
    return KRWCostBasis(quantity, cost, realized, missing, oversell)
