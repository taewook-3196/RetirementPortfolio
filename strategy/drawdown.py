"""
strategy/drawdown.py
최근 3개월 최고 종가 대비 하락폭(Drawdown) 및 Drawdown Score를 계산합니다.
공식:
recent_3m_high = 최근 3개월 최고 종가
drawdown = current_price / recent_3m_high - 1

Drawdown Score:
 0% ~  -5%: 0
-5% ~ -10%: 1
-10% ~ -15%: 2
-15% ~ -20%: 3
-20% 이하: 4
"""

from __future__ import annotations
from typing import Tuple


def calculate_drawdown(current_price: float, recent_3m_high: float) -> float:
    """
    최근 3개월 최고가 대비 현재가의 하락률을 계산합니다.
    최고가가 0 이하이거나 현재가가 더 높으면 0.0을 반환합니다.
    """
    if recent_3m_high <= 0:
        return 0.0
    if current_price >= recent_3m_high:
        return 0.0
    return (current_price / recent_3m_high) - 1.0


def calculate_drawdown_score(drawdown: float) -> int:
    """
    하락률(Drawdown)에 따른 0~4점 점수를 반환합니다.
    """
    if drawdown > -0.05:
        return 0
    elif -0.10 < drawdown <= -0.05:
        return 1
    elif -0.15 < drawdown <= -0.10:
        return 2
    elif -0.20 < drawdown <= -0.15:
        return 3
    else:  # drawdown <= -0.20
        return 4


def get_additional_buy_by_tier(drawdown: float) -> int:
    """
    프롬프트 24번 항목: 하락률 구간별 추가매수 기본 금액 산정 (단위: 원)
    0% ~ -5%: 0원
    -5% ~ -10%: 2,000,000원
    -10% ~ -15%: 5,000,000원
    -15% ~ -20%: 10,000,000원
    -20% 이하: 15,000,000원
    """
    score = calculate_drawdown_score(drawdown)
    mapping = {
        0: 0,
        1: 2000000,
        2: 5000000,
        3: 10000000,
        4: 15000000,
    }
    return mapping.get(score, 0)
