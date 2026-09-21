"""
strategy/allocation.py
포트폴리오 비중 및 비중 차이(Weight Gap)와 Weight Gap Score를 계산합니다.
공식:
current_weight = asset_value / portfolio_value
weight_gap = target_weight - current_weight
목표비중보다 현재비중이 낮을수록(weight_gap > 0) 매수 우선순위가 높아집니다.
"""

from __future__ import annotations
from typing import Dict, Any, List


def calculate_current_weights(holdings: Dict[str, float]) -> Dict[str, float]:
    """
    각 종목의 평가금액 {ticker: asset_value}을 받아
    전체 평가금액 대비 현재 비중 {ticker: current_weight}을 반환합니다.
    """
    total_val = sum(holdings.values())
    if total_val <= 0:
        return {ticker: 0.0 for ticker in holdings}
    return {ticker: val / total_val for ticker, val in holdings.items()}


def calculate_weight_gap(target_weight: float, current_weight: float) -> float:
    """
    목표비중과 현재비중의 차이를 반환합니다 (target - current).
    양수이면 목표비중 대비 부족(추가매수 필요), 음수이면 초과 상태.
    """
    return target_weight - current_weight


def calculate_weight_gap_score(weight_gap: float) -> float:
    """
    비중 차이에 대한 점수를 0.0~4.0 척도로 정규화합니다.
    - weight_gap <= 0 인 경우: 0.0 (목표비중 초과 시 가산점 없음)
    - weight_gap > 0 인 경우: 부족할수록 높은 점수 부여 (예: 20%p 부족 시 4.0점 만점)
    """
    if weight_gap <= 0:
        return 0.0
    # 25%p 부족 시 4.0점 (최대치 4.0 캡)
    score = (weight_gap / 0.25) * 4.0
    return min(max(score, 0.0), 4.0)
