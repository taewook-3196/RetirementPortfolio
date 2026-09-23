"""
strategy/rebalancing.py

추가 매수 자금이 없을 때 현재 보유 자산을 기준으로 작동하는
리밸런싱 권장 엔진.

[리밸런싱 규칙]

하락 구간
- 최근 3개월 고점 대비 5% 이내 하락: HOLD
- 5% 초과 ~ 10% 하락: BUY 10%
- 10% 초과 ~ 15% 하락: BUY 20%
- 15% 초과 하락: BUY 30%

상승 구간
- 최근 3개월 고점 대비 20% 이하 상승: HOLD
- 20% 초과 상승: 상승률의 50% 비율로 익절 매도

예:
- +10% 상승 -> HOLD
- +20% 상승 -> HOLD
- +21% 상승 -> 보유자산의 10.5% 매도
- +30% 상승 -> 보유자산의 15% 매도

기타
- 매수/매도 금액은 1만원 단위로 계산
- 소수점 보유 수량 지원
- 매도 시 실제 보유 수량을 초과하지 않도록 제한
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass
class ETFRebalanceInput:
    ticker: str
    name: str
    target_weight: float
    current_price: float
    recent_3m_high: float

    # 미국 주식 등의 소수점 수량 지원
    holding_quantity: float = 0.0

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

    action: str
    action_label: str
    action_rate: float

    recommended_amount: float
    recommended_shares: float

    expected_asset_value_after: float
    expected_weight_after: float

    reason: str


def _round_amount(
    amount: float,
) -> float:
    """
    매수/매도 권장 금액을 1만원 단위로 반올림합니다.
    """
    return float(
        round(
            float(amount),
            -4,
        )
    )


def calculate_rebalance_tier(
    change_pct: float,
) -> Tuple[str, str, float]:
    """
    최근 3개월 고점 대비 등락률에 따라
    리밸런싱 행동과 적용 비율을 반환합니다.

    반환:
        (action, action_label, rate)
    """

    change_pct = float(
        change_pct or 0
    )

    # -------------------------------------------------------------
    # 1. 상승 구간
    # -------------------------------------------------------------
    #
    # +20%까지는 익절하지 않습니다.
    # +20%를 초과했을 때만 상승률의 절반 비율을 매도합니다.
    #
    # 예:
    # +20% -> HOLD
    # +21% -> 10.5% SELL
    # +30% -> 15% SELL
    # -------------------------------------------------------------

    if change_pct > 0.20:
        profit_rate = (
            change_pct * 0.5
        )

        return (
            "SELL",
            f"{profit_rate * 100:.1f}% 익절 매도",
            profit_rate,
        )

    # -------------------------------------------------------------
    # 2. 유지 구간
    # -------------------------------------------------------------
    #
    # -5% 이상 ~ +20% 이하
    # -------------------------------------------------------------

    if change_pct >= -0.05:
        return (
            "HOLD",
            "유지 (0%)",
            0.0,
        )

    # -------------------------------------------------------------
    # 3. 하락 구간
    # -------------------------------------------------------------

    if change_pct >= -0.10:
        return (
            "BUY",
            "10% 추가 매수",
            0.10,
        )

    if change_pct >= -0.15:
        return (
            "BUY",
            "20% 추가 매수",
            0.20,
        )

    # -15%보다 더 하락하면 30% 추가매수
    return (
        "BUY",
        "30% 추가 매수",
        0.30,
    )


def generate_rebalancing_recommendations(
    inputs: List[ETFRebalanceInput],
    total_portfolio_value: float = 0.0,
) -> Dict[str, Any]:
    """
    현재 보유 자산과 시장 가격을 바탕으로
    리밸런싱 권장 결과를 생성합니다.
    """

    # -------------------------------------------------------------
    # 입력이 없는 경우
    # -------------------------------------------------------------

    if not inputs:
        return {
            "summary": {
                "total_portfolio_value": 0.0,
                "total_sell_amount": 0.0,
                "total_buy_amount": 0.0,
                "net_cash_flow": 0.0,
                "expected_total_portfolio_value": 0.0,
            },
            "recommendations": [],
        }

    # -------------------------------------------------------------
    # 전체 포트폴리오 평가액 계산
    # -------------------------------------------------------------

    total_portfolio_value = float(
        total_portfolio_value or 0
    )

    if total_portfolio_value <= 0:
        total_portfolio_value = sum(
            max(
                0.0,
                float(
                    item.current_asset_value
                    or 0
                ),
            )
            for item in inputs
        )

    results: List[
        ETFRebalanceResult
    ] = []

    total_sell_amount = 0.0
    total_buy_amount = 0.0

    # -------------------------------------------------------------
    # 종목별 계산
    # -------------------------------------------------------------

    for item in inputs:
        target_weight = max(
            0.0,
            float(
                item.target_weight
                or 0
            ),
        )

        current_price = max(
            0.0,
            float(
                item.current_price
                or 0
            ),
        )

        recent_high = max(
            0.0,
            float(
                item.recent_3m_high
                or 0
            ),
        )

        holding_quantity = max(
            0.0,
            float(
                item.holding_quantity
                or 0
            ),
        )

        current_asset_value = max(
            0.0,
            float(
                item.current_asset_value
                or 0
            ),
        )

        # ---------------------------------------------------------
        # 현재 비중
        # ---------------------------------------------------------

        if total_portfolio_value > 0:
            current_weight = (
                current_asset_value
                / total_portfolio_value
            )
        else:
            current_weight = 0.0

        # ---------------------------------------------------------
        # 기준 고점
        # ---------------------------------------------------------

        if recent_high > 0:
            reference_high = (
                recent_high
            )
        else:
            reference_high = (
                current_price
            )

        # ---------------------------------------------------------
        # 고점 대비 등락률
        # ---------------------------------------------------------

        if reference_high > 0:
            change_pct = (
                current_price
                - reference_high
            ) / reference_high
        else:
            change_pct = 0.0

        (
            action,
            action_label,
            action_rate,
        ) = calculate_rebalance_tier(
            change_pct
        )

        # ---------------------------------------------------------
        # 목표 비중이 0 이하인 종목은
        # 하락에 따른 추가 매수 대상에서 제외
        # ---------------------------------------------------------

        if (
            target_weight <= 0
            and action == "BUY"
        ):
            action = "HOLD"
            action_label = "유지 (0%)"
            action_rate = 0.0

        # ---------------------------------------------------------
        # 기준 자산 계산
        # ---------------------------------------------------------

        base_asset = (
            current_asset_value
        )

        # 미보유 종목이면서 BUY 신호인 경우
        # 목표비중 기준 가상 자산금액을 사용
        if (
            base_asset <= 0
            and total_portfolio_value > 0
            and action == "BUY"
            and target_weight > 0
        ):
            base_asset = (
                total_portfolio_value
                * target_weight
            )

        # ---------------------------------------------------------
        # 권장 금액 계산
        # ---------------------------------------------------------

        if (
            action == "HOLD"
            or action_rate <= 0
            or base_asset <= 0
        ):
            recommended_amount = 0.0
            recommended_shares = 0.0

        else:
            raw_amount = (
                base_asset
                * action_rate
            )

            recommended_amount = (
                _round_amount(
                    raw_amount
                )
            )

            if (
                current_price > 0
                and recommended_amount > 0
            ):
                recommended_shares = (
                    recommended_amount
                    / current_price
                )
            else:
                recommended_shares = 0.0

        # ---------------------------------------------------------
        # SELL
        # ---------------------------------------------------------

        if action == "SELL":
            # 보유 수량이 없으면 매도할 수 없음
            if holding_quantity <= 0:
                recommended_amount = 0.0
                recommended_shares = 0.0

                action = "HOLD"
                action_label = "유지 (0%)"
                action_rate = 0.0

            else:
                # 실제 보유 수량을 초과하지 않도록 제한
                recommended_shares = min(
                    recommended_shares,
                    holding_quantity,
                )

                recommended_amount = (
                    recommended_shares
                    * current_price
                )

                # 실제 매도 가능 금액이 현재 평가금액을
                # 초과하지 않도록 한 번 더 제한
                recommended_amount = min(
                    recommended_amount,
                    current_asset_value,
                )

                if current_price > 0:
                    recommended_shares = min(
                        holding_quantity,
                        recommended_amount
                        / current_price,
                    )

                total_sell_amount += (
                    recommended_amount
                )

            expected_asset_value_after = max(
                0.0,
                current_asset_value
                - recommended_amount,
            )

        # ---------------------------------------------------------
        # BUY
        # ---------------------------------------------------------

        elif action == "BUY":
            total_buy_amount += (
                recommended_amount
            )

            expected_asset_value_after = (
                current_asset_value
                + recommended_amount
            )

        # ---------------------------------------------------------
        # HOLD
        # ---------------------------------------------------------

        else:
            recommended_amount = 0.0
            recommended_shares = 0.0

            expected_asset_value_after = (
                current_asset_value
            )

        # ---------------------------------------------------------
        # 추천 사유
        # ---------------------------------------------------------

        if action == "HOLD":
            if change_pct < 0:
                reason = (
                    "최근 3개월 고점 대비 "
                    f"{abs(change_pct) * 100:.1f}% 하락했지만 "
                    "추가 매수 기준에 도달하지 않아 "
                    "현 비중 유지를 권장합니다."
                )

            elif change_pct <= 0.20:
                reason = (
                    "최근 3개월 고점 대비 "
                    f"{change_pct * 100:+.1f}% 수준으로, "
                    "익절 기준인 +20%를 초과하지 않아 "
                    "현 비중 유지를 권장합니다."
                )

            else:
                reason = (
                    "현재 조건에서는 매도 가능한 "
                    "보유 수량이 없어 현 상태를 유지합니다."
                )

        elif action == "BUY":
            reason = (
                "최근 3개월 고점 대비 "
                f"{abs(change_pct) * 100:.1f}% 하락하여 "
                f"{action_rate * 100:.0f}% 추가 매수 "
                f"(약 {recommended_amount:,.0f}원, "
                f"{recommended_shares:,.4f}주)를 "
                "권장합니다."
            )

        elif action == "SELL":
            reason = (
                "최근 3개월 고점 대비 "
                f"{change_pct * 100:+.1f}% 상승하여 "
                "+20% 익절 기준을 초과했습니다. "
                "상승률의 절반에 해당하는 "
                f"{action_rate * 100:.1f}% 비율로 "
                f"약 {recommended_amount:,.0f}원, "
                f"{recommended_shares:,.4f}주 "
                "익절 매도를 권장합니다."
            )

        else:
            reason = (
                "현 비중 유지를 권장합니다."
            )

        # ---------------------------------------------------------
        # 결과 저장
        # ---------------------------------------------------------

        results.append(
            ETFRebalanceResult(
                ticker=item.ticker,
                name=item.name,
                target_weight=target_weight,
                current_weight=current_weight,
                current_price=current_price,
                reference_high=reference_high,
                price_change_pct=change_pct,
                action=action,
                action_label=action_label,
                action_rate=action_rate,
                recommended_amount=(
                    recommended_amount
                ),
                recommended_shares=(
                    recommended_shares
                ),
                expected_asset_value_after=(
                    expected_asset_value_after
                ),
                expected_weight_after=0.0,
                reason=reason,
            )
        )

    # -------------------------------------------------------------
    # 리밸런싱 후 예상 비중 재계산
    # -------------------------------------------------------------

    expected_total_post = sum(
        result.expected_asset_value_after
        for result in results
    )

    if expected_total_post > 0:
        for result in results:
            result.expected_weight_after = (
                result.expected_asset_value_after
                / expected_total_post
            )

    else:
        for result in results:
            result.expected_weight_after = (
                result.target_weight
            )

    # -------------------------------------------------------------
    # 요약
    # -------------------------------------------------------------

    summary = {
        "total_portfolio_value": (
            total_portfolio_value
        ),
        "total_sell_amount": (
            total_sell_amount
        ),
        "total_buy_amount": (
            total_buy_amount
        ),
        "net_cash_flow": (
            total_sell_amount
            - total_buy_amount
        ),
        "expected_total_portfolio_value": (
            expected_total_post
        ),
    }

    return {
        "summary": summary,
        "recommendations": results,
    }
