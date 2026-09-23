"""
portfolio/holdings.py

개별 종목의 보유 현황 및 성과 계산 모듈.

- BUY / SELL 거래를 시간순으로 반영
- 이동평균 매수가 계산
- 보유수량 및 현재 평가금액 계산
- 평가손익 및 실현손익 계산
- 분배금/배당금 집계
- PostgreSQL Numeric(Decimal) 값을 안전하게 float로 변환
- 국내 ETF 및 향후 미국 주식의 소수점 수량 지원
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from database.models import Dividend, Price, Transaction


@dataclass
class ETFPosition:
    ticker: str
    name: str = ""

    # 미국 주식의 소수점 수량까지 지원하기 위해 float 사용
    quantity: float = 0.0

    # 현재 보유분의 총 매수원가
    total_buy_cost: float = 0.0

    # 이동평균 매수가
    average_buy_price: float = 0.0

    # 최근 시장 가격
    current_price: float = 0.0

    # 현재 평가금액
    current_value: float = 0.0

    # 평가손익
    unrealized_pnl: float = 0.0

    # 평가수익률
    unrealized_roi: float = 0.0

    # 실현손익
    realized_pnl: float = 0.0

    # 누적 분배금/배당금
    total_dividends: float = 0.0

    # 총손익
    total_pnl: float = 0.0

    # 누적 수수료 및 제세금
    total_fees: float = 0.0


def _to_float(value) -> float:
    """
    PostgreSQL Numeric에서 반환되는 Decimal 값을 포함하여
    숫자 값을 안전하게 float로 변환합니다.
    """
    if value is None:
        return 0.0

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def calculate_etf_positions(
    transactions: List[Transaction],
    dividends: List[Dividend],
    latest_prices: Dict[str, Price],
    ticker_names: Optional[Dict[str, str]] = None,
) -> Dict[str, ETFPosition]:
    """
    거래 내역과 분배금 내역을 시간순으로 재생하여
    종목별 포지션, 평단가 및 손익을 계산합니다.
    """
    positions: Dict[str, ETFPosition] = {}

    names_map = ticker_names or {}

    # ---------------------------------------------------------
    # 종목별 거래 분류
    # ---------------------------------------------------------
    tx_by_ticker: Dict[str, List[Transaction]] = {}

    for tx in transactions:
        tx_by_ticker.setdefault(
            tx.ticker,
            [],
        ).append(tx)

    # ---------------------------------------------------------
    # 종목별 분배금/배당금 분류
    # ---------------------------------------------------------
    div_by_ticker: Dict[str, List[Dividend]] = {}

    for dividend in dividends:
        div_by_ticker.setdefault(
            dividend.ticker,
            [],
        ).append(dividend)

    # 거래 종목뿐 아니라 목표 종목도 포지션에 표시
    all_tickers = set(
        tx_by_ticker.keys()
    ).union(
        names_map.keys()
    )

    # ---------------------------------------------------------
    # 종목별 포지션 계산
    # ---------------------------------------------------------
    for ticker in all_tickers:
        position = ETFPosition(
            ticker=ticker,
            name=names_map.get(
                ticker,
                ticker,
            ),
        )

        current_quantity = 0.0
        total_cost = 0.0
        average_price = 0.0
        realized_pnl = 0.0
        total_fees = 0.0

        # -----------------------------------------------------
        # 거래내역 시간순 처리
        # -----------------------------------------------------
        transaction_list = sorted(
            tx_by_ticker.get(
                ticker,
                [],
            ),
            key=lambda tx: (
                tx.transaction_date,
                tx.id or 0,
            ),
        )

        for tx in transaction_list:
            quantity = _to_float(
                tx.quantity
            )

            price = _to_float(
                tx.price
            )

            fee = _to_float(
                tx.fee
            )

            tax = _to_float(
                tx.tax
            )

            total_fees += fee + tax

            transaction_type = (
                str(tx.transaction_type)
                .strip()
                .upper()
            )

            # -------------------------------------------------
            # 매수
            # -------------------------------------------------
            if transaction_type == "BUY":
                if quantity <= 0:
                    continue

                buy_amount = (
                    quantity * price
                ) + fee

                new_quantity = (
                    current_quantity
                    + quantity
                )

                if new_quantity > 0:
                    average_price = (
                        (
                            current_quantity
                            * average_price
                        )
                        + buy_amount
                    ) / new_quantity

                current_quantity = (
                    new_quantity
                )

                total_cost = (
                    current_quantity
                    * average_price
                )

            # -------------------------------------------------
            # 매도
            # -------------------------------------------------
            elif transaction_type == "SELL":
                if quantity <= 0:
                    continue

                # 보유 수량보다 많은 매도 기록이 있어도
                # 음수 보유량이 되지 않도록 제한
                sell_quantity = min(
                    quantity,
                    current_quantity,
                )

                if sell_quantity <= 0:
                    continue

                realized = (
                    sell_quantity * price
                    - sell_quantity * average_price
                    - fee
                    - tax
                )

                realized_pnl += realized

                current_quantity -= (
                    sell_quantity
                )

                # 부동소수점 오차로 아주 작은 값이
                # 남는 경우 0으로 정리
                if abs(current_quantity) < 1e-12:
                    current_quantity = 0.0

                total_cost = (
                    current_quantity
                    * average_price
                )

                if current_quantity <= 0:
                    current_quantity = 0.0
                    total_cost = 0.0
                    average_price = 0.0

        # -----------------------------------------------------
        # 분배금/배당금 합산
        # -----------------------------------------------------
        dividend_list = (
            div_by_ticker.get(
                ticker,
                [],
            )
        )

        total_dividends = sum(
            _to_float(
                dividend.net_amount
            )
            for dividend in dividend_list
        )

        # -----------------------------------------------------
        # 현재가
        # -----------------------------------------------------
        price_object = (
            latest_prices.get(
                ticker
            )
        )

        if price_object:
            current_price = _to_float(
                price_object.close_price
            )
        else:
            # 아직 시장 가격이 없다면 평단가를 임시 사용하여
            # 평가금액이 갑자기 0원이 되는 것을 방지
            current_price = (
                average_price
                if average_price > 0
                else 0.0
            )

        # -----------------------------------------------------
        # 평가금액 및 손익
        # -----------------------------------------------------
        current_value = (
            current_quantity
            * current_price
        )

        unrealized_pnl = (
            current_value
            - total_cost
        )

        if total_cost > 0:
            unrealized_roi = (
                unrealized_pnl
                / total_cost
            )
        else:
            unrealized_roi = 0.0

        total_pnl = (
            unrealized_pnl
            + realized_pnl
            + total_dividends
        )

        # -----------------------------------------------------
        # 결과 저장
        # -----------------------------------------------------
        position.quantity = (
            current_quantity
        )

        position.total_buy_cost = round(
            total_cost,
            2,
        )

        position.average_buy_price = round(
            average_price,
            4,
        )

        position.current_price = round(
            current_price,
            4,
        )

        position.current_value = round(
            current_value,
            2,
        )

        position.unrealized_pnl = round(
            unrealized_pnl,
            2,
        )

        position.unrealized_roi = round(
            unrealized_roi,
            6,
        )

        position.realized_pnl = round(
            realized_pnl,
            2,
        )

        position.total_dividends = round(
            total_dividends,
            2,
        )

        position.total_pnl = round(
            total_pnl,
            2,
        )

        position.total_fees = round(
            total_fees,
            2,
        )

        positions[ticker] = position

    return positions
