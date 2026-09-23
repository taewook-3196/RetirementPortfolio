"""
strategy/recommendation.py
개인 퇴직연금 ETF 월간 매수 의사결정 추천 엔진.
- 기본 매수금(1,000만원) 배분
- 하락률 구간별 추가 매수금(200만~1,500만) 산정
- 월간 추가매수 한도(1,500만원) 준수 (월 최대 매수: 2,500만원)
- 총 투자원금(1억원) 잔액 한도 체크 및 자동 조정
- 목표비중 초과 종목 추가매수 제한
- 매수 후 예상 비중 계산
- 친절하고 직관적인 자연어 추천 사유 자동 생성
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from strategy.drawdown import (
    calculate_drawdown,
    calculate_drawdown_score,
    get_additional_buy_by_tier,
)
from strategy.allocation import (
    calculate_weight_gap,
    calculate_weight_gap_score,
    calculate_current_weights,
)
from strategy.buy_signal import calculate_priority_score


@dataclass
class ETFRecommendationInput:
    ticker: str
    name: str
    target_weight: float
    current_price: float
    recent_3m_high: float
    holding_quantity: int = 0
    current_asset_value: float = 0.0


@dataclass
class ETFRecommendationResult:
    ticker: str
    name: str
    target_weight: float
    current_weight: float
    weight_gap: float
    recent_high: float
    current_price: float
    drawdown: float
    drawdown_score: int
    weight_gap_score: float
    priority_score: float
    base_buy: int
    additional_buy: int
    recommended_buy: int
    expected_weight_after: float
    reason: str


def generate_recommendations(
    inputs: List[ETFRecommendationInput],
    initial_capital: int = 100000000,
    base_monthly: int = 10000000,
    max_additional_monthly: int = 15000000,
    total_invested_so_far: int = 0,
    already_invested_in_cycle: bool = False,
    cycle_desc: str = "",
) -> Dict[str, Any]:
    """
    모든 포트폴리오 데이터를 종합하여 종목별 최종 매수 추천 결과를 산출합니다.
    - already_invested_in_cycle=True인 경우 해당 주기에 이미 납입(매수)한 이력이 있으므로 추가 매수 추천을 0원으로 제한합니다.
    """
    if not inputs:
        remaining_cash = max(0, initial_capital - total_invested_so_far)
        summary = {
            "initial_capital": initial_capital,
            "total_invested_so_far": total_invested_so_far,
            "remaining_cash": remaining_cash,
            "base_monthly_budget": base_monthly,
            "total_additional_buy": 0,
            "total_recommended_buy": 0,
            "total_portfolio_value_now": 0.0,
            "total_portfolio_value_expected": 0.0,
            "already_invested_in_cycle": already_invested_in_cycle,
            "cycle_desc": cycle_desc,
        }
        return {"summary": summary, "recommendations": []}

    # 1. 포트폴리오 총 평가액 및 현재 비중 계산
    total_portfolio_value = sum(item.current_asset_value for item in inputs)
    weights_map = {}
    if total_portfolio_value > 0:
        for item in inputs:
            weights_map[item.ticker] = item.current_asset_value / total_portfolio_value
    else:
        for item in inputs:
            weights_map[item.ticker] = 0.0

    # 2. 1차 분석: 낙폭, 스코어, 추가매수 요구액 계산
    parsed_items = []
    total_requested_additional = 0

    for item in inputs:
        cur_weight = weights_map[item.ticker]
        weight_gap = calculate_weight_gap(item.target_weight, cur_weight)
        drawdown = calculate_drawdown(item.current_price, item.recent_3m_high)
        dd_score = calculate_drawdown_score(drawdown)
        wg_score = calculate_weight_gap_score(weight_gap)
        priority_score = calculate_priority_score(dd_score, wg_score, weight_gap)

        # 추가매수 금액 결정
        # 단, 목표비중 초과(weight_gap <= 0)이거나 이미 이번 주기에 납입(매수)한 경우 추가매수 제외
        if weight_gap <= 0 or already_invested_in_cycle:
            raw_additional = 0
        else:
            raw_additional = get_additional_buy_by_tier(drawdown)

        total_requested_additional += raw_additional

        parsed_items.append({
            "item": item,
            "cur_weight": cur_weight,
            "weight_gap": weight_gap,
            "drawdown": drawdown,
            "dd_score": dd_score,
            "wg_score": wg_score,
            "priority_score": priority_score,
            "raw_additional": raw_additional,
        })

    # 3. 월간 추가매수 한도(max_additional_monthly) 적용
    # 만약 각 종목 추가매수 합계가 한도를 넘으면 우선순위 점수 비례 배분
    effective_max_additional = 0 if already_invested_in_cycle else max_additional_monthly
    if total_requested_additional > effective_max_additional:
        total_p_score = sum(p["priority_score"] for p in parsed_items if p["raw_additional"] > 0)
        for p in parsed_items:
            if p["raw_additional"] > 0 and total_p_score > 0 and effective_max_additional > 0:
                ratio = p["priority_score"] / total_p_score
                p["capped_additional"] = int(round(effective_max_additional * ratio, -4))
            else:
                p["capped_additional"] = 0
        actual_total_additional = min(sum(p["capped_additional"] for p in parsed_items), effective_max_additional)
    else:
        for p in parsed_items:
            p["capped_additional"] = p["raw_additional"]
        actual_total_additional = total_requested_additional

    # 4. 기본 매수금(base_monthly) 배분
    # 기본 매수금은 목표비중에 맞추어 분배 (비중 부족분 우선 또는 목표비중 비례)
    # 초기 진입이거나 고른 비중 유지를 위해 target_weight 비례를 기본으로 하되 부족분 가중
    total_base_budget = base_monthly
    for p in parsed_items:
        item = p["item"]
        # 목표비중 초과 시 기본 매수 비중을 축소하고 부족한 곳에 더 배정
        p["base_buy"] = int(round(total_base_budget * item.target_weight, -4))

    # 5. 투자금 한도 체크 (remaining_cash = initial_capital - total_invested_so_far)
    remaining_cash = max(0, initial_capital - total_invested_so_far)
    total_planned_buy = sum(p["base_buy"] + p["capped_additional"] for p in parsed_items)

    cash_scale_factor = 1.0
    if total_planned_buy > remaining_cash:
        cash_scale_factor = remaining_cash / total_planned_buy if total_planned_buy > 0 else 0.0

    # 6. 최종 추천 결과 리스트 생성 및 추천 사유 작성
    results: List[ETFRecommendationResult] = []
    final_total_recommended = 0
    final_total_portfolio_post = total_portfolio_value + min(total_planned_buy, remaining_cash)

    for p in parsed_items:
        item: ETFRecommendationInput = p["item"]
        base_b = int(round(p["base_buy"] * cash_scale_factor, -4))
        add_b = int(round(p["capped_additional"] * cash_scale_factor, -4))
        final_buy = base_b + add_b
        final_total_recommended += final_buy

        post_asset_val = item.current_asset_value + final_buy
        expected_weight = (post_asset_val / final_total_portfolio_post) if final_total_portfolio_post > 0 else item.target_weight

        # 자연어 추천 사유 생성 (프롬프트 47번)
        reasons = []
        wg_pct = round(p["weight_gap"] * 100, 1)
        dd_pct = round(p["drawdown"] * 100, 1)

        if item.target_weight <= 0:
            reasons.append("목표 비중이 미설정(0.0%)된 종목으로, 정량 매수 추천에서 제외됩니다.")
        elif p["weight_gap"] <= 0:
            reasons.append(
                f"현재 비중({round(p['cur_weight']*100, 1)}%)이 목표비중({round(item.target_weight*100, 1)}%)을 초과하여 추가매수를 제한합니다."
            )
        elif already_invested_in_cycle:
            p_desc = cycle_desc if cycle_desc else "이번 주기"
            reasons.append(
                f"목표비중 대비 {abs(wg_pct)}%p 부족하나, {p_desc}에 이미 납입(매수) 이력이 있어 이번 주기 추가 매수를 추천하지 않습니다."
            )
        else:
            reasons.append(
                f"목표비중 대비 {abs(wg_pct)}%p 부족하며 최근 3개월 고점 대비 {abs(dd_pct)}% 하락했습니다."
            )

        if add_b > 0:
            reasons.append(f"낙폭 구간에 따른 추가 매수금 {add_b:,}원이 가산되었습니다.")
        elif p["raw_additional"] > 0 and add_b == 0 and cash_scale_factor < 1.0:
            reasons.append("투자 가능 원금 잔액 한도로 인해 추가 매수가 제한되었습니다.")

        if cash_scale_factor < 1.0 and final_buy < (p["base_buy"] + p["capped_additional"]):
            reasons.append(f"남은 투자 원금({remaining_cash:,}원)에 맞추어 매수 금액이 자동 조정되었습니다.")

        reason_text = " ".join(reasons)

        results.append(
            ETFRecommendationResult(
                ticker=item.ticker,
                name=item.name,
                target_weight=item.target_weight,
                current_weight=p["cur_weight"],
                weight_gap=p["weight_gap"],
                recent_high=item.recent_3m_high,
                current_price=item.current_price,
                drawdown=p["drawdown"],
                drawdown_score=p["dd_score"],
                weight_gap_score=p["wg_score"],
                priority_score=p["priority_score"],
                base_buy=base_b,
                additional_buy=add_b,
                recommended_buy=final_buy,
                expected_weight_after=expected_weight,
                reason=reason_text,
            )
        )

    summary = {
        "initial_capital": initial_capital,
        "total_invested_so_far": total_invested_so_far,
        "remaining_cash": remaining_cash,
        "base_monthly_budget": base_monthly,
        "total_additional_buy": sum(r.additional_buy for r in results),
        "total_recommended_buy": final_total_recommended,
        "total_portfolio_value_now": total_portfolio_value,
        "total_portfolio_value_expected": final_total_portfolio_post,
        "already_invested_in_cycle": already_invested_in_cycle,
        "cycle_desc": cycle_desc,
    }

    return {"summary": summary, "recommendations": results}
