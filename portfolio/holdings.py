"""
portfolio/holdings.py
개별 ETF 보유 현황 및 성과 계산 모듈.
- 거래내역(BUY, SELL)을 기반으로 한 이동평균 매수가(평단가) 산출
- 보유수량, 현재가, 현재평가액 산출
- 평가손익 및 평가수익률 계산
- 매도에 따른 실현손익 및 분배금 집계
- 총손익 산출
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from database.models import Transaction, Dividend, Price


@dataclass
class ETFPosition:
    ticker: str
    name: str = ""
    quantity: int = 0
    total_buy_cost: float = 0.0      # 현재 보유분에 대한 총 매수원가
    average_buy_price: float = 0.0   # 이동평균 매수가
    current_price: float = 0.0       # 최근 시장 가격
    current_value: float = 0.0       # 현재 평가금액 (quantity * current_price)
    unrealized_pnl: float = 0.0      # 평가손익
    unrealized_roi: float = 0.0      # 평가수익률 (unrealized_pnl / total_buy_cost)
    realized_pnl: float = 0.0        # 실현손익
    total_dividends: float = 0.0     # 누적 분배금
    total_pnl: float = 0.0           # 총손익 (평가손익 + 실현손익 + 분배금)
    total_fees: float = 0.0          # 누적 수수료 및 제세금


def calculate_etf_positions(
    transactions: List[Transaction],
    dividends: List[Dividend],
    latest_prices: Dict[str, Price],
    ticker_names: Optional[Dict[str, str]] = None,
) -> Dict[str, ETFPosition]:
    """
    거래 내역과 분배금 내역을 시간순으로 재생(replay)하여 종목별 포지션 및 평단가를 계산합니다.
    """
    positions: Dict[str, ETFPosition] = {}
    names_map = ticker_names or {}

    # 종목별 거래 분류
    tx_by_ticker: Dict[str, List[Transaction]] = {}
    for tx in transactions:
        tx_by_ticker.setdefault(tx.ticker, []).append(tx)

    # 종목별 분배금 분류
    div_by_ticker: Dict[str, List[Dividend]] = {}
    for div in dividends:
        div_by_ticker.setdefault(div.ticker, []).append(div)

    all_tickers = set(tx_by_ticker.keys()).union(names_map.keys())

    for ticker in all_tickers:
        pos = ETFPosition(
            ticker=ticker,
            name=names_map.get(ticker, ticker),
        )

        cur_qty = 0
        total_cost = 0.0
        avg_price = 0.0
        realized = 0.0
        fees = 0.0

        # 거래내역 시간순 정렬 및 반영
        tx_list = sorted(tx_by_ticker.get(ticker, []), key=lambda x: (x.transaction_date, x.id))
        for tx in tx_list:
            fees += (tx.fee or 0.0) + (tx.tax or 0.0)
            tx_type = tx.transaction_type.upper()

            if tx_type == "BUY":
                buy_qty = tx.quantity
                buy_price = tx.price
                buy_amount = (buy_qty * buy_price) + (tx.fee or 0.0)

                new_qty = cur_qty + buy_qty
                if new_qty > 0:
                    avg_price = ((cur_qty * avg_price) + buy_amount) / new_qty
                cur_qty = new_qty
                total_cost = cur_qty * avg_price

            elif tx_type == "SELL":
                sell_qty = min(tx.quantity, cur_qty)
                sell_price = tx.price
                # 실현손익 = 매도금액 - (매도수량 * 평단가) - 매도수수료/제세금
                pnl = (sell_qty * sell_price) - (sell_qty * avg_price) - (tx.fee or 0.0) - (tx.tax or 0.0)
                realized += pnl

                cur_qty -= sell_qty
                total_cost = cur_qty * avg_price
                if cur_qty == 0:
                    avg_price = 0.0

        # 분배금 합산
        div_list = div_by_ticker.get(ticker, [])
        div_total = sum(d.net_amount for d in div_list)

        # 현재가 반영 (시세 데이터가 아직 없는 경우 보유 평단가를 fallback으로 사용하여 평가금 0원 방지)
        p_obj = latest_prices.get(ticker)
        current_price = p_obj.close_price if p_obj else (avg_price if avg_price > 0 else 0.0)
        if p_obj and p_obj.name and not pos.name:
            pos.name = p_obj.name

        current_val = cur_qty * current_price
        unrealized = current_val - total_cost
        unrealized_roi = (unrealized / total_cost) if total_cost > 0 else 0.0
        total_pnl = unrealized + realized + div_total

        pos.quantity = cur_qty
        pos.total_buy_cost = round(total_cost, 2)
        pos.average_buy_price = round(avg_price, 2)
        pos.current_price = current_price
        pos.current_value = round(current_val, 2)
        pos.unrealized_pnl = round(unrealized, 2)
        pos.unrealized_roi = round(unrealized_roi, 4)
        pos.realized_pnl = round(realized, 2)
        pos.total_dividends = round(div_total, 2)
        pos.total_pnl = round(total_pnl, 2)
        pos.total_fees = round(fees, 2)

        positions[ticker] = pos

    return positions
