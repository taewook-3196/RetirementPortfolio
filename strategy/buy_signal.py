"""
strategy/buy_signal.py
하락 점수와 비중 부족 점수를 결합하여 ETF별 우선순위 점수(Priority Score)를 산출합니다.
공식 (프롬프트 31번):
priority_score = drawdown_score * 0.7 + weight_gap_score * 0.3
단, weight_gap <= 0 (목표비중 달성 또는 초과)이면 우선순위를 0 또는 매우 낮게 처리합니다.
"""

from __future__ import annotations


def calculate_priority_score(
    drawdown_score: int,
    weight_gap_score: float,
    weight_gap: float,
    drawdown_weight: float = 0.7,
    weight_gap_weight: float = 0.3,
) -> float:
    """
    종합 우선순위 점수를 산출합니다.
    - weight_gap <= 0 인 경우: 비중 초과이므로 추가매수 우선순위를 0.0으로 제한
    - weight_gap > 0 인 경우: 가중합 공식 적용
    """
    if weight_gap <= 0:
        return 0.0

    raw_score = (drawdown_score * drawdown_weight) + (weight_gap_score * weight_gap_weight)
    return round(raw_score, 4)
