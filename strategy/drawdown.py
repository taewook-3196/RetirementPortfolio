"""
strategy/drawdown.py

최근 3개월 최고 종가 대비 하락폭(Drawdown)을 계산하고,
계좌별 추가매수 한도에 적용할 추가매수 비율을 결정합니다.

하락폭별 추가매수 비율:
  0% ~  -5% 미만 :   0%
 -5% ~ -10% 미만 :  25%
-10% ~ -15% 미만 :  50%
-15% ~ -20% 미만 :  75%
-20% 이하        : 100%

추가매수 금액 자체는 이 파일에서 결정하지 않습니다.
실제 금액은 각 계좌의 max_additional_monthly에
아래 비율을 적용하여 계산합니다.
"""

from __future__ import annotations


def calculate_drawdown(
    current_price: float,
    recent_3m_high: float,
) -> float:
    """
    최근 3개월 최고가 대비 현재가의 하락률을 계산합니다.

    예:
        최고가 100
        현재가 90
        -> -0.10 (-10%)
    """
    current_price = float(
        current_price or 0
    )

    recent_3m_high = float(
        recent_3m_high or 0
    )

    if recent_3m_high <= 0:
        return 0.0

    if current_price <= 0:
        return 0.0

    if current_price >= recent_3m_high:
        return 0.0

    return (
        current_price
        / recent_3m_high
        - 1.0
    )


def calculate_drawdown_score(
    drawdown: float,
) -> int:
    """
    하락률에 따른 0~4점 점수를 반환합니다.

    -5% 도달  -> 1
    -10% 도달 -> 2
    -15% 도달 -> 3
    -20% 도달 -> 4
    """
    drawdown = float(
        drawdown or 0
    )

    if drawdown > -0.05:
        return 0

    if drawdown > -0.10:
        return 1

    if drawdown > -0.15:
        return 2

    if drawdown > -0.20:
        return 3

    return 4


def get_additional_buy_ratio(
    drawdown: float,
) -> float:
    """
    하락률에 따라 계좌의 월 추가매수 한도 중
    현재까지 사용할 수 있는 누적 비율을 반환합니다.

    score 0 ->   0%
    score 1 ->  25%
    score 2 ->  50%
    score 3 ->  75%
    score 4 -> 100%
    """
    score = (
        calculate_drawdown_score(
            drawdown
        )
    )

    mapping = {
        0: 0.00,
        1: 0.25,
        2: 0.50,
        3: 0.75,
        4: 1.00,
    }

    return float(
        mapping.get(
            score,
            0.0,
        )
    )


def get_additional_buy_by_tier(
    drawdown: float,
    max_additional_budget: float = 0.0,
) -> float:
    """
    하위 호환용 함수.

    기존 코드가 이 함수명을 사용하는 경우에도
    계좌별 추가매수 한도를 기준으로 금액을 계산합니다.

    새 코드에서는 가능하면
    get_additional_buy_ratio()를 직접 사용합니다.
    """
    max_additional_budget = max(
        0.0,
        float(
            max_additional_budget
            or 0
        ),
    )

    return (
        max_additional_budget
        * get_additional_buy_ratio(
            drawdown
        )
    )
