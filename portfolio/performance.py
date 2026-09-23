"""
portfolio/performance.py

전체 포트폴리오 성과 요약 및 지표 계산 모듈.

- 총 투자원금
- 현재 평가금액
- 평가손익 및 실현손익
- 누적 분배금/배당금
- 총 손익 및 총 수익률
- 남은 투자 가능 금액
- 현재 보유 종목 수
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from portfolio.holdings import ETFPosition


@dataclass
class PortfolioSummary:
    # 설정된 초기 총 투자금 한도
    initial_capital: float

    # 현재 보유분의 총 매수원가
    total_invested: float

    # 현재 총 평가금액
    total_current_value: float

    # 총 평가손익
    total_unrealized_pnl: float

    # 총 실현손익
    total_realized_pnl: float

    # 총 누적 분배금/배당금
    total_dividends: float

    # 평가손익 + 실현손익 + 분배금/배당금
    total_pnl: float

    # 총 손익 / 현재 보유분 총 매수원가
    total_roi: float

    # 초기 투자 한도 - 현재 보유분 총 매수원가
    remaining_cash: float

    # 현재 수량이 0보다 큰 종목 수
    position_count: int


def calculate_portfolio_summary(
    positions: Dict[str, ETFPosition],
    initial_capital: float = 100_000_000.0,
) -> PortfolioSummary:
    """
    모든 종목의 포지션을 합산하여
    전체 포트폴리오 성과 요약을 계산합니다.
    """

    capital = float(initial_capital or 0)

    total_invested = sum(
        float(position.total_buy_cost or 0)
        for position in positions.values()
    )

    total_current_value = sum(
        float(position.current_value or 0)
        for position in positions.values()
    )

    total_unrealized_pnl = sum(
        float(position.unrealized_pnl or 0)
        for position in positions.values()
    )

    total_realized_pnl = sum(
        float(position.realized_pnl or 0)
        for position in positions.values()
    )

    total_dividends = sum(
        float(position.total_dividends or 0)
        for position in positions.values()
    )

    total_pnl = (
        total_unrealized_pnl
        + total_realized_pnl
        + total_dividends
    )

    if total_invested > 0:
        total_roi = (
            total_pnl
            / total_invested
        )
    else:
        total_roi = 0.0

    remaining_cash = max(
        0.0,
        capital - total_invested,
    )

    active_positions = sum(
        1
        for position in positions.values()
        if float(position.quantity or 0) > 0
    )

    return PortfolioSummary(
        initial_capital=round(capital, 2),
        total_invested=round(
            total_invested,
            2,
        ),
        total_current_value=round(
            total_current_value,
            2,
        ),
        total_unrealized_pnl=round(
            total_unrealized_pnl,
            2,
        ),
        total_realized_pnl=round(
            total_realized_pnl,
            2,
        ),
        total_dividends=round(
            total_dividends,
            2,
        ),
        total_pnl=round(
            total_pnl,
            2,
        ),
        total_roi=round(
            total_roi,
            6,
        ),
        remaining_cash=round(
            remaining_cash,
            2,
        ),
        position_count=active_positions,
    )
