"""
portfolio/performance.py
전체 포트폴리오 성과 요약 및 지표를 계산합니다 (프롬프트 42번 항목).
- 총 투자원금
- 현재 평가금액
- 총 손익
- 총 수익률
- 누적 분배금
- 남은 투자금 (initial_capital - total_invested)
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, List
from portfolio.holdings import ETFPosition


@dataclass
class PortfolioSummary:
    initial_capital: int              # 설정된 초기 총 투자금 한도 (예: 1억원)
    total_invested: float             # 누적 실투자 매수 원금
    total_current_value: float        # 현재 총 평가금액
    total_unrealized_pnl: float       # 총 평가손익
    total_realized_pnl: float         # 총 실현손익
    total_dividends: float            # 총 누적 분배금
    total_pnl: float                  # 종합 손익 (평가손익 + 실현손익 + 분배금)
    total_roi: float                  # 종합 수익률
    remaining_cash: float             # 남은 투자금 한도 (initial_capital - total_invested)
    position_count: int               # 보유 종목 수


def calculate_portfolio_summary(
    positions: Dict[str, ETFPosition],
    initial_capital: int = 100000000,
) -> PortfolioSummary:
    """
    모든 ETF 포지션을 취합하여 전체 포트폴리오 종합 성과 요약 지표를 산출합니다.
    """
    total_invested = sum(pos.total_buy_cost for pos in positions.values())
    total_current_val = sum(pos.current_value for pos in positions.values())
    total_unrealized = sum(pos.unrealized_pnl for pos in positions.values())
    total_realized = sum(pos.realized_pnl for pos in positions.values())
    total_divs = sum(pos.total_dividends for pos in positions.values())

    total_pnl = total_unrealized + total_realized + total_divs
    total_roi = (total_pnl / total_invested) if total_invested > 0 else 0.0
    remaining_cash = max(0.0, float(initial_capital) - total_invested)
    active_positions = sum(1 for pos in positions.values() if pos.quantity > 0)

    return PortfolioSummary(
        initial_capital=initial_capital,
        total_invested=round(total_invested, 2),
        total_current_value=round(total_current_val, 2),
        total_unrealized_pnl=round(total_unrealized, 2),
        total_realized_pnl=round(total_realized, 2),
        total_dividends=round(total_divs, 2),
        total_pnl=round(total_pnl, 2),
        total_roi=round(total_roi, 4),
        remaining_cash=round(remaining_cash, 2),
        position_count=active_positions,
    )
