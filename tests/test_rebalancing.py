"""
tests/test_rebalancing.py
자산 기준 리밸런싱 권장 엔진 및 6가지 구간 규칙 단위 테스트.
"""

import pytest
from strategy.rebalancing import (
    calculate_rebalance_tier,
    ETFRebalanceInput,
    generate_rebalancing_recommendations,
)


def test_rebalance_tiers_exact_rules():
    """사용자가 지정한 6가지 리밸런싱 구간 규칙 정확도 검증"""
    # 1. 5% 이내 감소 -> 유지
    action, label, rate = calculate_rebalance_tier(-0.03)
    assert action == "HOLD"
    assert "유지" in label
    assert rate == 0.0

    action, label, rate = calculate_rebalance_tier(-0.05)
    assert action == "HOLD"
    assert rate == 0.0

    # 2. 5~10% 감소 -> 10% 추가 매수
    action, label, rate = calculate_rebalance_tier(-0.07)
    assert action == "BUY"
    assert "10% 추가 매수" in label
    assert rate == 0.10

    # 3. 10~15% 감소 -> 20% 추가 매수
    action, label, rate = calculate_rebalance_tier(-0.12)
    assert action == "BUY"
    assert "20% 추가 매수" in label
    assert rate == 0.20

    # 4. 15~20% 감소 -> 30% 추가 매수
    action, label, rate = calculate_rebalance_tier(-0.18)
    assert action == "BUY"
    assert "30% 추가 매수" in label
    assert rate == 0.30

    # 4-1. 20% 초과 감소 -> 30% 추가 매수
    action, label, rate = calculate_rebalance_tier(-0.25)
    assert action == "BUY"
    assert "30% 추가 매수" in label
    assert rate == 0.30

    # 5. 5% 이내 증가 -> 유지
    action, label, rate = calculate_rebalance_tier(0.02)
    assert action == "HOLD"
    assert "유지" in label
    assert rate == 0.0

    action, label, rate = calculate_rebalance_tier(0.05)
    assert action == "HOLD"
    assert rate == 0.0

    # 6. 5% 이상 증가 -> 증가 비율 * 0.5 익절
    # 예: 10% 증가 시 5% 익절
    action, label, rate = calculate_rebalance_tier(0.10)
    assert action == "SELL"
    assert "5.0% 익절 매도" in label
    assert pytest.approx(rate, 0.001) == 0.05

    # 예: 20% 증가 시 10% 익절
    action, label, rate = calculate_rebalance_tier(0.20)
    assert action == "SELL"
    assert "10.0% 익절 매도" in label
    assert pytest.approx(rate, 0.001) == 0.10


def test_generate_rebalancing_recommendations_flow():
    """자산 기준 리밸런싱 종합 시나리오 검증"""
    inputs = [
        # ETF 1: 10% 하락 (고점 20,000 -> 현재 18,000, -10% -> 10% 추가매수)
        # 보유 1,000주 = 1,800만원 -> 10% 추가매수 = 180만원 (100주)
        ETFRebalanceInput(
            ticker="111111",
            name="ETF_하락",
            target_weight=0.5,
            current_price=18000.0,
            recent_3m_high=20000.0,
            holding_quantity=1000,
            current_asset_value=18000000.0,
        ),
        # ETF 2: 10% 상승 (고점 10,000 -> 현재 11,000, +10% -> 5% 익절)
        # 보유 2,000주 = 2,200만원 -> 5% 익절 = 110만원 (100주)
        ETFRebalanceInput(
            ticker="222222",
            name="ETF_상승",
            target_weight=0.5,
            current_price=11000.0,
            recent_3m_high=10000.0,
            holding_quantity=2000,
            current_asset_value=22000000.0,
        ),
    ]

    res = generate_rebalancing_recommendations(inputs, total_portfolio_value=40000000.0)
    summary = res["summary"]
    recs = res["recommendations"]

    assert len(recs) == 2

    # ETF 1: BUY
    r1 = recs[0]
    assert r1.action == "BUY"
    assert r1.action_rate == 0.10
    assert r1.recommended_amount == 1800000
    assert r1.recommended_shares == 100

    # ETF 2: SELL
    r2 = recs[1]
    assert r2.action == "SELL"
    assert pytest.approx(r2.action_rate, 0.001) == 0.05
    assert r2.recommended_amount == 1100000
    assert r2.recommended_shares == 100

    # Summary
    assert summary["total_buy_amount"] == 1800000
    assert summary["total_sell_amount"] == 1100000
    assert summary["net_cash_flow"] == 1100000 - 1800000  # -700,000원
