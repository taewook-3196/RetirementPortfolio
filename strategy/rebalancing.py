"""
strategy/rebalancing.py
추가 매수 자금이 없을 때 현재 보유 자산을 기준으로 작동하는 리밸런싱 권장 엔진.

[리밸런싱 규칙]
- 현재 주가가 최근 3개월 고점 대비 5% 이내 감소: 유지 (HOLD)
- 현재 주가가 최근 3개월 고점 대비 5~10% 감소: 10% 추가 매수 (BUY 10%)
- 현재 주가가 최근 3개월 고점 대비 10~15% 감소: 20% 추가 매수 (BUY 20%)
- 현재 주가가 최근 3개월 고점 대비 15~20% 감소: 30% 추가 매수 (BUY 30%)
- 현재 주가가 최근 3개월 고점 대비 20% 초과 감소: 30% 추가 매수 (BUY 30%)
- 현재 주가가 최근 3개월 고점 대비 5% 이내 증가: 유지 (HOLD)
- 현재 주가가 최근 3개월 고점 대비 5% 이상 증가: 증가 비율 * 0.5 익절 매도 (SELL, 예: 10% 증가 시 5% 익절)
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple


@dataclass
class ETFRebalanceInput:
    ticker: str
    name: str
    target_weight: float
    current_price: float
    recent_3m_high: float
    holding_quantity: int = 0
    current_asset_value: float = 0.0


@dataclass
class ETFRebalanceResult:
    ticker: str
    name: str
    target_weight: float
    current_weight: float
    current_price: float
    reference_high: float
    price_change_pct: float
    action: str            # "HOLD", "BUY", "SELL"
    action_label: str      # "유지", "10% 추가 매수", "5.0% 익절 매도" 등
    action_rate: float     # 비율 (0.10, 0.20, 0.05 등)
    recommended_amount: int  # 권장 금액 (매수: 양수, 매도: 음수 또는 양수로 표기)
    recommended_shares: int  # 권장 주수
    expected_asset_value_after: float
    expected_weight_after: float
    reason: str


def calculate_rebalance_tier(change_pct: float) -> Tuple[str, str, float]:
    """
    고점 대비 등락률(change_pct)에 따른 리밸런싱 행동, 라벨, 적용 비율을 반환합니다.
    반환: (action, action_label, rate)
    """
    # 1. 상승 구간
    if change_pct > 0.05:
        profit_rate = change_pct * 0.5
        return ("SELL", f"{profit_rate * 100:.1f}% 익절 매도", profit_rate)
    elif change_pct >= -0.05:
        # -5% ~ +5% 구간
        return ("HOLD", "유지 (0%)", 0.0)

    # 2. 하락 구간 (change_pct < -0.05)
    if -0.10 <= change_pct < -0.05:
        return ("BUY", "10% 추가 매수", 0.10)
    elif -0.15 <= change_pct < -0.10:
        return ("BUY", "20% 추가 매수", 0.20)
    elif -0.20 <= change_pct < -0.15:
        return ("BUY", "30% 추가 매수", 0.30)
    else:  # change_pct < -0.20
        return ("BUY", "30% 추가 매수", 0.30)


def generate_rebalancing_recommendations(
    inputs: List[ETFRebalanceInput],
    total_portfolio_value: float = 0.0,
) -> Dict[str, Any]:
    """
    현재 보유 자산과 시장 가격을 바탕으로 자산 기준 리밸런싱 권장 결과를 생성합니다.
    """
    if not inputs:
        return {
            "summary": {
                "total_portfolio_value": 0.0,
                "total_sell_amount": 0,
                "total_buy_amount": 0,
                "net_cash_flow": 0,
            },
            "recommendations": [],
        }

    # 전체 포트폴리오 평가액 합산 (인자로 전달되지 않은 경우 inputs 기준)
    if total_portfolio_value <= 0:
        total_portfolio_value = sum(item.current_asset_value for item in inputs)

    results: List[ETFRebalanceResult] = []
    total_sell_amt = 0
    total_buy_amt = 0

    for item in inputs:
        cur_weight = (item.current_asset_value / total_portfolio_value) if total_portfolio_value > 0 else 0.0
        ref_high = item.recent_3m_high if item.recent_3m_high > 0 else item.current_price

        # 고점 대비 등락률 계산
        if ref_high > 0:
            change_pct = (item.current_price - ref_high) / ref_high
        else:
            change_pct = 0.0

        action, action_label, rate = calculate_rebalance_tier(change_pct)

        # 기준 자산 결정:
        # 이미 보유 중이면 보유 평가금액 기준, 미보유(0원) 종목이면 총자산*목표비중 가상 기준
        base_asset = item.current_asset_value
        if base_asset <= 0 and total_portfolio_value > 0 and action == "BUY":
            base_asset = total_portfolio_value * item.target_weight

        if action == "HOLD" or rate == 0.0 or base_asset <= 0:
            rec_amount = 0
            rec_shares = 0
        else:
            raw_amt = base_asset * rate
            rec_amount = int(round(raw_amt, -4))  # 만원 단위 반올림
            rec_shares = int(rec_amount // item.current_price) if item.current_price > 0 else 0

        # 매도 시 보유 수량 초과 방지
        if action == "SELL":
            if rec_shares > item.holding_quantity:
                rec_shares = item.holding_quantity
                rec_amount = int(round(rec_shares * item.current_price, -4))
            total_sell_amt += rec_amount
            post_asset = max(0.0, item.current_asset_value - rec_amount)
        elif action == "BUY":
            total_buy_amt += rec_amount
            post_asset = item.current_asset_value + rec_amount
        else:
            post_asset = item.current_asset_value

        # 사유 텍스트 생성
        change_str = f"{change_pct * 100:+.2f}%"
        if action == "HOLD":
            if change_pct < 0:
                reason = f"최근 3개월 고점 대비 {abs(change_pct)*100:.1f}% 하락하였으나, 5% 이내의 안정 구간이어서 현 비중 유지를 권장합니다."
            else:
                reason = f"최근 3개월 고점 대비 {change_pct*100:+.1f}% 수준으로, 5% 이내의 통상적 변동 구간이어서 현 비중 유지를 권장합니다."
        elif action == "BUY":
            reason = (
                f"최근 3개월 고점 대비 {abs(change_pct)*100:.1f}% 하락 구간에 진입하여, "
                f"보유 자산의 {rate*100:.0f}% 추가 매수(+{rec_amount:,}원, 약 {rec_shares:,}주)를 권장합니다."
            )
        elif action == "SELL":
            reason = (
                f"최근 3개월 고점 대비 {change_pct*100:+.1f}% 상승하여 수익 실현 구간입니다. "
                f"증가율의 절반인 {rate*100:.1f}% 익절 매도(-{rec_amount:,}원, 약 {rec_shares:,}주)를 권장합니다."
            )
        else:
            reason = "현 비중 유지"

        results.append(
            ETFRebalanceResult(
                ticker=item.ticker,
                name=item.name,
                target_weight=item.target_weight,
                current_weight=cur_weight,
                current_price=item.current_price,
                reference_high=ref_high,
                price_change_pct=change_pct,
                action=action,
                action_label=action_label,
                action_rate=rate,
                recommended_amount=rec_amount,
                recommended_shares=rec_shares,
                expected_asset_value_after=post_asset,
                expected_weight_after=0.0,  # 아래에서 사후 총자산으로 계산
                reason=reason,
            )
        )

    # 사후 예상 비중 재계산
    expected_total_post = sum(r.expected_asset_value_after for r in results)
    if expected_total_post > 0:
        for r in results:
            r.expected_weight_after = r.expected_asset_value_after / expected_total_post
    else:
        for r in results:
            r.expected_weight_after = r.target_weight

    summary = {
        "total_portfolio_value": total_portfolio_value,
        "total_sell_amount": total_sell_amt,
        "total_buy_amount": total_buy_amt,
        "net_cash_flow": total_sell_amt - total_buy_amt,
        "expected_total_portfolio_value": expected_total_post,
    }

    return {
        "summary": summary,
        "recommendations": results,
    }
