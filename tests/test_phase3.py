"""
tests/test_phase3.py
Phase 3 검증 테스트:
- strategy/drawdown.py (하락률, 하락 스코어, 구간별 추가매수금)
- strategy/allocation.py (비중 차이, 비중 스코어)
- strategy/buy_signal.py (우선순위 점수 및 비중 초과 시 제한)
- strategy/recommendation.py (월간 매수 배분, 월 1500만 한도, 원금 잔액 한도, 추천 이유 생성)
"""

import pytest
from strategy.drawdown import (
    calculate_drawdown,
    calculate_drawdown_score,
    get_additional_buy_by_tier,
)
from strategy.allocation import (
    calculate_weight_gap,
    calculate_weight_gap_score,
)
from strategy.buy_signal import calculate_priority_score
from strategy.recommendation import (
    ETFRecommendationInput,
    generate_recommendations,
)


def test_drawdown_formulas():
    """Drawdown 및 Drawdown Score 계산 정확성 검증"""
    assert calculate_drawdown(100, 100) == 0.0
    assert calculate_drawdown(105, 100) == 0.0
    assert round(calculate_drawdown(94, 100), 4) == -0.06
    assert round(calculate_drawdown(88, 100), 4) == -0.12
    assert round(calculate_drawdown(82, 100), 4) == -0.18
    assert round(calculate_drawdown(75, 100), 4) == -0.25

    # 구간별 스코어 (0, 1, 2, 3, 4)
    assert calculate_drawdown_score(-0.02) == 0
    assert calculate_drawdown_score(-0.06) == 1
    assert calculate_drawdown_score(-0.12) == 2
    assert calculate_drawdown_score(-0.18) == 3
    assert calculate_drawdown_score(-0.25) == 4

    # 추가매수 금액 기준
    assert get_additional_buy_by_tier(-0.03) == 0
    assert get_additional_buy_by_tier(-0.07) == 2000000
    assert get_additional_buy_by_tier(-0.12) == 5000000
    assert get_additional_buy_by_tier(-0.18) == 10000000
    assert get_additional_buy_by_tier(-0.24) == 15000000


def test_priority_score():
    """Priority Score 및 비중 초과 시 0 처리 검증"""
    # weight_gap > 0 (부족) -> 점수 계산
    score = calculate_priority_score(drawdown_score=2, weight_gap_score=2.0, weight_gap=0.05)
    # 2 * 0.7 + 2.0 * 0.3 = 1.4 + 0.6 = 2.0
    assert score == 2.0

    # weight_gap <= 0 (목표비중 달성/초과) -> 반드시 0.0
    score_overweight = calculate_priority_score(drawdown_score=4, weight_gap_score=0.0, weight_gap=-0.03)
    assert score_overweight == 0.0


def test_recommendation_scenario_drawdown_tiers():
    """ETF별 하락에 따른 추가매수 반영 검증 (Scenario B, C)"""
    inputs = [
        # TDF: -6% 하락 (티어 1: +200만원, 비중 17M/30M = 56.7% < 60%)
        ETFRecommendationInput(
            ticker="442560",
            name="RISE TDF2040액티브",
            target_weight=0.60,
            current_price=15040,
            recent_3m_high=16000,
            current_asset_value=17000000,
        ),
        # S&P500: -12% 하락 (티어 2: +500만원, 비중 6M/30M = 20.0% < 25%)
        ETFRecommendationInput(
            ticker="488500",
            name="TIGER 미국S&P500동일가중",
            target_weight=0.25,
            current_price=10560,
            recent_3m_high=12000,
            current_asset_value=6000000,
        ),
        # NASDAQ: -2% 하락 (티어 0: +0원, 비중 7M/30M = 23.3% > 15%)
        ETFRecommendationInput(
            ticker="494840",
            name="TIGER 미국나스닥TOP10",
            target_weight=0.15,
            current_price=14700,
            recent_3m_high=15000,
            current_asset_value=7000000,
        ),
    ]

    res = generate_recommendations(
        inputs,
        initial_capital=100000000,
        base_monthly=10000000,
        max_additional_monthly=15000000,
        total_invested_so_far=30000000,
    )

    recs = {r.ticker: r for r in res["recommendations"]}
    assert recs["442560"].additional_buy == 2000000
    assert recs["488500"].additional_buy == 5000000
    assert recs["494840"].additional_buy == 0

    # 총 매수금 = 기본(1,000만) + 추가(700만) = 1,700만원
    assert res["summary"]["total_recommended_buy"] == 17000000
    assert "추가 매수금" in recs["488500"].reason


def test_overweight_etf_restriction():
    """목표비중 초과 ETF는 낙폭이 크더라도 추가매수가 0원으로 제한되는지 검증 (프롬프트 32번)"""
    inputs = [
        # TDF가 35M/50M = 70%로 목표비중(60%) 초과인 상태에서 -15% 하락
        ETFRecommendationInput(
            ticker="442560",
            name="RISE TDF2040액티브",
            target_weight=0.60,
            current_price=13600,
            recent_3m_high=16000,
            current_asset_value=35000000,
        ),
        ETFRecommendationInput(
            ticker="488500",
            name="TIGER 미국S&P500동일가중",
            target_weight=0.25,
            current_price=12000,
            recent_3m_high=12000,
            current_asset_value=10000000,
        ),
        ETFRecommendationInput(
            ticker="494840",
            name="TIGER 미국나스닥TOP10",
            target_weight=0.15,
            current_price=15000,
            recent_3m_high=15000,
            current_asset_value=5000000,
        ),
    ]

    res = generate_recommendations(inputs, initial_capital=100000000, base_monthly=10000000)
    recs = {r.ticker: r for r in res["recommendations"]}

    # TDF는 15% 하락했으나 비중 초과이므로 추가매수 0원
    assert recs["442560"].additional_buy == 0
    assert "추가매수를 제한합니다" in recs["442560"].reason


def test_monthly_additional_cap():
    """월간 추가매수 한도 (1,500만원) 준수 검증"""
    inputs = [
        # TDF -18% (1000만 요구)
        ETFRecommendationInput(
            ticker="442560",
            name="RISE TDF2040액티브",
            target_weight=0.60,
            current_price=8200,
            recent_3m_high=10000,
            current_asset_value=10000000,
        ),
        # S&P -22% (1500만 요구) -> 합계 2500만 요구 (1500만 초과)
        ETFRecommendationInput(
            ticker="488500",
            name="TIGER 미국S&P500동일가중",
            target_weight=0.25,
            current_price=7800,
            recent_3m_high=10000,
            current_asset_value=5000000,
        ),
        ETFRecommendationInput(
            ticker="494840",
            name="TIGER 미국나스닥TOP10",
            target_weight=0.15,
            current_price=10000,
            recent_3m_high=10000,
            current_asset_value=3000000,
        ),
    ]

    res = generate_recommendations(
        inputs,
        initial_capital=100000000,
        base_monthly=10000000,
        max_additional_monthly=15000000,
        total_invested_so_far=18000000,
    )

    # 전체 추가매수 합계가 1,500만원 이하로 제한되는지 확인
    assert res["summary"]["total_additional_buy"] <= 15000000


def test_initial_capital_remaining_limit():
    """초기 투자금 한도(1억) 잔여 금액 초과 방지 검증"""
    inputs = [
        ETFRecommendationInput(
            ticker="442560",
            name="RISE TDF2040액티브",
            target_weight=0.60,
            current_price=15000,
            recent_3m_high=16000,
            current_asset_value=60000000,
        ),
        ETFRecommendationInput(
            ticker="488500",
            name="TIGER 미국S&P500동일가중",
            target_weight=0.25,
            current_price=11000,
            recent_3m_high=12000,
            current_asset_value=25000000,
        ),
        ETFRecommendationInput(
            ticker="494840",
            name="TIGER 미국나스닥TOP10",
            target_weight=0.15,
            current_price=14000,
            recent_3m_high=15000,
            current_asset_value=10000000,
        ),
    ]

    # 총 9,500만원 투자되어 잔여금이 500만원뿐인 상황
    res = generate_recommendations(
        inputs,
        initial_capital=100000000,
        base_monthly=10000000,
        max_additional_monthly=15000000,
        total_invested_so_far=95000000,
    )

    # 추천 매수금의 총합은 잔여 투자금(500만원)을 초과할 수 없음
    assert res["summary"]["total_recommended_buy"] <= 5000000
    for r in res["recommendations"]:
        if r.recommended_buy > 0:
            assert "남은 투자 원금" in r.reason
