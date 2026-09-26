"""
strategy/recommendation.py

계좌별 매수 한도와 목표 비중, 최근 낙폭을 이용하여
종목별 매수 추천을 계산합니다.

핵심 원칙:
- 기본 매수 예산은 RecommendationService에서 계산한
  '이번 주기 남은 기본 매수 한도'를 사용합니다.
- 추가매수는 최근 3개월 고점 대비 낙폭에 따라
  계좌의 월 추가매수 한도의 0/25/50/75/100%를
  누적 허용합니다.
- 이미 사용한 추가매수 금액은
  additional_budget_used로 차감합니다.
- 목표 비중이 0이거나 현재 비중이 목표 이상인 종목에는
  추가매수를 추천하지 않습니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from strategy.allocation import (
    calculate_weight_gap,
    calculate_weight_gap_score,
)
from strategy.buy_signal import (
    calculate_priority_score,
)
from strategy.drawdown import (
    calculate_drawdown,
    calculate_drawdown_score,
    get_additional_buy_ratio,
)


@dataclass
class ETFRecommendationInput:
    ticker: str
    name: str
    target_weight: float
    current_price: float
    recent_3m_high: float
    holding_quantity: float = 0.0
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

    base_buy: float
    additional_buy: float
    recommended_buy: float

    expected_weight_after: float
    reason: str


def _round_buy_amount(
    amount: float,
) -> float:
    """
    추천 매수액을 1만원 단위로 반올림합니다.
    """
    amount = max(
        0.0,
        float(
            amount or 0
        ),
    )

    return float(
        round(
            amount,
            -4,
        )
    )


def generate_recommendations(
    inputs: List[ETFRecommendationInput],
    initial_capital: float = 100_000_000.0,
    base_monthly: float = 10_000_000.0,
    max_additional_monthly: float = 0.0,
    total_invested_so_far: float = 0.0,
    already_invested_in_cycle: bool = False,
    cycle_desc: str = "",
    additional_budget_used: float = 0.0,
) -> Dict[str, Any]:
    """
    종목별 매수 추천을 계산합니다.

    주의:
    base_monthly는 이 함수에서는
    '이번 주기 남은 기본 매수 예산'입니다.

    max_additional_monthly는
    계좌에 설정된 전체 월 추가매수 한도입니다.

    additional_budget_used는
    이번 주기에 이미 사용한 추가매수 금액입니다.

    already_invested_in_cycle은 기존 호출부와의
    호환성을 위해 유지하지만 매수 차단 조건으로
    사용하지 않습니다.
    """

    initial_capital = max(
        0.0,
        float(
            initial_capital or 0
        ),
    )

    remaining_base_budget = max(
        0.0,
        float(
            base_monthly or 0
        ),
    )

    max_additional_monthly = max(
        0.0,
        float(
            max_additional_monthly
            or 0
        ),
    )

    additional_budget_used = max(
        0.0,
        float(
            additional_budget_used
            or 0
        ),
    )

    total_invested_so_far = max(
        0.0,
        float(
            total_invested_so_far
            or 0
        ),
    )

    remaining_cash = max(
        0.0,
        initial_capital
        - total_invested_so_far,
    )

    if not inputs:
        return {
            "summary": {
                "initial_capital":
                    initial_capital,

                "total_invested_so_far":
                    total_invested_so_far,

                "remaining_cash":
                    remaining_cash,

                "base_monthly_budget":
                    remaining_base_budget,

                "max_additional_budget":
                    max_additional_monthly,

                "additional_budget_used":
                    additional_budget_used,

                "additional_budget_allowed":
                    0.0,

                "remaining_additional_buy":
                    0.0,

                "additional_buy_triggered":
                    False,

                "total_additional_buy":
                    0.0,

                "total_recommended_buy":
                    0.0,

                "total_portfolio_value_now":
                    0.0,

                "total_portfolio_value_expected":
                    0.0,

                "already_invested_in_cycle":
                    already_invested_in_cycle,

                "cycle_desc":
                    cycle_desc,
            },
            "recommendations": [],
        }

    # ---------------------------------------------------------
    # 1. 현재 포트폴리오 비중
    # ---------------------------------------------------------

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

    weights_map: Dict[
        str,
        float,
    ] = {}

    for item in inputs:

        value = max(
            0.0,
            float(
                item.current_asset_value
                or 0
            ),
        )

        if total_portfolio_value > 0:
            weights_map[item.ticker] = (
                value
                / total_portfolio_value
            )
        else:
            weights_map[item.ticker] = 0.0

    # ---------------------------------------------------------
    # 2. 종목별 낙폭/비중/우선순위 계산
    # ---------------------------------------------------------

    parsed_items: List[
        Dict[str, Any]
    ] = []

    highest_additional_ratio = 0.0

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

        current_asset_value = max(
            0.0,
            float(
                item.current_asset_value
                or 0
            ),
        )

        current_weight = (
            weights_map.get(
                item.ticker,
                0.0,
            )
        )

        weight_gap = (
            calculate_weight_gap(
                target_weight,
                current_weight,
            )
        )

        drawdown = (
            calculate_drawdown(
                current_price,
                recent_high,
            )
        )

        drawdown_score = (
            calculate_drawdown_score(
                drawdown
            )
        )

        weight_gap_score = (
            calculate_weight_gap_score(
                weight_gap
            )
        )

        priority_score = (
            calculate_priority_score(
                drawdown_score,
                weight_gap_score,
                weight_gap,
            )
        )

        additional_ratio = 0.0

        if (
            target_weight > 0
            and weight_gap > 0
        ):
            additional_ratio = (
                get_additional_buy_ratio(
                    drawdown
                )
            )

        highest_additional_ratio = max(
            highest_additional_ratio,
            additional_ratio,
        )

        parsed_items.append(
            {
                "item":
                    item,

                "target_weight":
                    target_weight,

                "current_price":
                    current_price,

                "recent_high":
                    recent_high,

                "current_asset_value":
                    current_asset_value,

                "cur_weight":
                    current_weight,

                "weight_gap":
                    float(
                        weight_gap
                    ),

                "drawdown":
                    float(
                        drawdown
                    ),

                "dd_score":
                    int(
                        drawdown_score
                    ),

                "wg_score":
                    float(
                        weight_gap_score
                    ),

                "priority_score":
                    float(
                        priority_score
                    ),

                "additional_ratio":
                    additional_ratio,
            }
        )

    # ---------------------------------------------------------
    # 3. 현재 낙폭 단계에서 허용되는 추가매수 누적액
    # ---------------------------------------------------------

    allowed_additional_budget = (
        max_additional_monthly
        * highest_additional_ratio
    )

    remaining_additional_budget = max(
        0.0,
        allowed_additional_budget
        - additional_budget_used,
    )

    additional_buy_triggered = (
        highest_additional_ratio > 0
        and
        remaining_additional_budget > 0
    )

    # ---------------------------------------------------------
    # 4. 기본 매수 예산 배분
    #
    # 목표비중보다 부족한 종목에만 배분한다.
    # 부족 정도를 기준으로 비례 배분한다.
    # ---------------------------------------------------------

    eligible_base_items = [
        parsed
        for parsed in parsed_items
        if (
            parsed["target_weight"] > 0
            and parsed["weight_gap"] > 0
        )
    ]

    total_positive_gap = sum(
        max(
            0.0,
            float(
                parsed["weight_gap"]
            ),
        )
        for parsed in eligible_base_items
    )

    for parsed in parsed_items:

        if (
            parsed["target_weight"] <= 0
            or parsed["weight_gap"] <= 0
            or remaining_base_budget <= 0
        ):
            parsed["base_buy"] = 0.0

        elif total_positive_gap > 0:

            ratio = (
                parsed["weight_gap"]
                / total_positive_gap
            )

            parsed["base_buy"] = (
                _round_buy_amount(
                    remaining_base_budget
                    * ratio
                )
            )

        else:
            parsed["base_buy"] = 0.0

    # 반올림으로 기본 한도 초과 방지
    total_base_buy = sum(
        parsed["base_buy"]
        for parsed in parsed_items
    )

    if (
        total_base_buy
        > remaining_base_budget
        and total_base_buy > 0
    ):

        scale = (
            remaining_base_budget
            / total_base_buy
        )

        for parsed in parsed_items:
            parsed["base_buy"] = (
                _round_buy_amount(
                    parsed["base_buy"]
                    * scale
                )
            )

    # ---------------------------------------------------------
    # 5. 추가매수 예산 배분
    #
    # 각 종목의 낙폭 단계와 비중 부족 정도를 함께 반영합니다.
    #
    # 예:
    # - 종목 A 낙폭 -20% -> 추가매수 강도 100%
    # - 종목 B 낙폭 -5%  -> 추가매수 강도 25%
    #
    # 단순히 전체 예산을 동일 단계로 나누지 않고,
    # 각 종목의 낙폭 강도를 priority_score에 곱하여
    # 배분 가중치를 계산합니다.
    #
    # 전체 추가매수 금액은 현재 포트폴리오에서
    # 가장 높은 낙폭 단계가 허용하는 누적 한도를
    # 초과하지 않습니다.
    # ---------------------------------------------------------

    additional_candidates = [
        parsed
        for parsed in parsed_items
        if (
            parsed["target_weight"] > 0
            and parsed["weight_gap"] > 0
            and parsed["additional_ratio"] > 0
        )
    ]

    # 종목별 추가매수 배분 가중치
    #
    # priority_score:
    #   비중 부족 + 낙폭을 반영한 기존 우선순위
    #
    # additional_ratio:
    #   현재 낙폭 단계의 강도
    #   0.25 / 0.50 / 0.75 / 1.00
    #
    # 둘을 함께 사용하여 낙폭이 더 큰 종목이
    # 더 높은 추가매수 우선순위를 갖도록 합니다.
    for parsed in parsed_items:

        parsed[
            "additional_weight"
        ] = 0.0

        if (
            parsed["target_weight"] > 0
            and parsed["weight_gap"] > 0
            and parsed["additional_ratio"] > 0
        ):

            priority = max(
                0.0,
                float(
                    parsed[
                        "priority_score"
                    ]
                ),
            )

            gap = max(
                0.0,
                float(
                    parsed[
                        "weight_gap"
                    ]
                ),
            )

            # priority_score가 0인 특수 상황에서도
            # 비중 부족분을 fallback 가중치로 사용
            base_weight = (
                priority
                if priority > 0
                else gap
            )

            parsed[
                "additional_weight"
            ] = (
                base_weight
                * float(
                    parsed[
                        "additional_ratio"
                    ]
                )
            )

    total_additional_weight = sum(
        float(
            parsed[
                "additional_weight"
            ]
        )
        for parsed in additional_candidates
    )

    for parsed in parsed_items:

        parsed[
            "additional_buy"
        ] = 0.0

        if (
            remaining_additional_budget <= 0
            or parsed
            not in additional_candidates
        ):
            continue

        if total_additional_weight > 0:

            allocation_ratio = (
                float(
                    parsed[
                        "additional_weight"
                    ]
                )
                / total_additional_weight
            )

        else:

            allocation_ratio = (
                1.0
                / len(
                    additional_candidates
                )
            )

        parsed[
            "additional_buy"
        ] = _round_buy_amount(
            remaining_additional_budget
            * allocation_ratio
        )

    # ---------------------------------------------------------
    # 반올림으로 추가매수 허용액을 초과하는 경우 보정
    # ---------------------------------------------------------

    total_additional_buy = sum(
        float(
            parsed[
                "additional_buy"
            ]
        )
        for parsed in parsed_items
    )

    if (
        total_additional_buy
        > remaining_additional_budget
        and total_additional_buy > 0
    ):

        scale = (
            remaining_additional_budget
            / total_additional_buy
        )

        for parsed in parsed_items:

            if (
                parsed[
                    "additional_buy"
                ] <= 0
            ):
                continue

            parsed[
                "additional_buy"
            ] = _round_buy_amount(
                parsed[
                    "additional_buy"
                ]
                * scale
            )

        # 1만원 단위 반올림 후에도 아주 작은 초과가
        # 발생할 수 있으므로 마지막으로 다시 제한합니다.
        rounded_total = sum(
            float(
                parsed[
                    "additional_buy"
                ]
            )
            for parsed in parsed_items
        )

        if (
            rounded_total
            > remaining_additional_budget
        ):

            excess = (
                rounded_total
                - remaining_additional_budget
            )

            # 추천금액이 가장 큰 종목에서
            # 초과분을 제거합니다.
            largest_item = max(
                parsed_items,
                key=lambda item: float(
                    item[
                        "additional_buy"
                    ]
                ),
            )

            largest_item[
                "additional_buy"
            ] = max(
                0.0,
                float(
                    largest_item[
                        "additional_buy"
                    ]
                )
                - excess,
            )
    # ---------------------------------------------------------
    # 6. 전체 투자 가능 원금 한도
    # ---------------------------------------------------------

    total_planned_buy = sum(
        float(
            parsed["base_buy"]
        )
        + float(
            parsed["additional_buy"]
        )
        for parsed in parsed_items
    )

    if (
        total_planned_buy
        > remaining_cash
        and total_planned_buy > 0
    ):
        cash_scale_factor = (
            remaining_cash
            / total_planned_buy
        )
    else:
        cash_scale_factor = 1.0

    # ---------------------------------------------------------
    # 7. 최종 추천
    # ---------------------------------------------------------

    results: List[
        ETFRecommendationResult
    ] = []

    final_total_recommended = 0.0

    for parsed in parsed_items:

        item: ETFRecommendationInput = (
            parsed["item"]
        )

        base_buy = _round_buy_amount(
            parsed["base_buy"]
            * cash_scale_factor
        )

        additional_buy = (
            _round_buy_amount(
                parsed[
                    "additional_buy"
                ]
                * cash_scale_factor
            )
        )

        final_buy = (
            base_buy
            + additional_buy
        )

        available_for_item = max(
            0.0,
            remaining_cash
            - final_total_recommended,
        )

        if final_buy > available_for_item:

            final_buy = (
                available_for_item
            )

            if final_buy < base_buy:
                base_buy = final_buy
                additional_buy = 0.0
            else:
                additional_buy = max(
                    0.0,
                    final_buy
                    - base_buy,
                )

        final_total_recommended += (
            final_buy
        )

        results.append(
            ETFRecommendationResult(
                ticker=item.ticker,
                name=item.name,

                target_weight=parsed[
                    "target_weight"
                ],

                current_weight=parsed[
                    "cur_weight"
                ],

                weight_gap=parsed[
                    "weight_gap"
                ],

                recent_high=parsed[
                    "recent_high"
                ],

                current_price=parsed[
                    "current_price"
                ],

                drawdown=parsed[
                    "drawdown"
                ],

                drawdown_score=parsed[
                    "dd_score"
                ],

                weight_gap_score=parsed[
                    "wg_score"
                ],

                priority_score=parsed[
                    "priority_score"
                ],

                base_buy=base_buy,

                additional_buy=(
                    additional_buy
                ),

                recommended_buy=(
                    final_buy
                ),

                expected_weight_after=0.0,

                reason="",
            )
        )

    # ---------------------------------------------------------
    # 8. 예상 비중 및 추천 사유
    # ---------------------------------------------------------

    final_portfolio_value = (
        total_portfolio_value
        + final_total_recommended
    )

    for result, parsed in zip(
        results,
        parsed_items,
    ):

        post_asset_value = (
            parsed[
                "current_asset_value"
            ]
            + result.recommended_buy
        )

        if final_portfolio_value > 0:

            result.expected_weight_after = (
                post_asset_value
                / final_portfolio_value
            )

        else:

            result.expected_weight_after = (
                parsed[
                    "target_weight"
                ]
            )

        reasons: List[str] = []

        current_pct = (
            parsed["cur_weight"]
            * 100
        )

        target_pct = (
            parsed["target_weight"]
            * 100
        )

        gap_pct = (
            parsed["weight_gap"]
            * 100
        )

        drawdown_pct = (
            parsed["drawdown"]
            * 100
        )

        if parsed["target_weight"] <= 0:

            reasons.append(
                "목표 비중이 0%인 종목으로 "
                "매수 추천에서 제외됩니다."
            )

        elif parsed["weight_gap"] <= 0:

            reasons.append(
                f"현재 비중({current_pct:.1f}%)이 "
                f"목표 비중({target_pct:.1f}%) "
                "이상이므로 신규 매수를 제한합니다."
            )

        else:

            reasons.append(
                f"목표 비중 대비 "
                f"{abs(gap_pct):.1f}%p 부족합니다."
            )

            reasons.append(
                f"최근 3개월 고점 대비 "
                f"{abs(drawdown_pct):.1f}% "
                "하락 상태입니다."
            )

        if result.base_buy > 0:

            reasons.append(
                "이번 주기 남은 기본 매수 한도에서 "
                f"{result.base_buy:,.0f}원이 "
                "배정되었습니다."
            )

        if result.additional_buy > 0:

            ratio_pct = (
                parsed[
                    "additional_ratio"
                ]
                * 100
            )

            reasons.append(
                f"현재 낙폭 단계에 따라 "
                f"추가매수 한도의 "
                f"{ratio_pct:.0f}% 단계가 "
                "활성화되어 "
                f"{result.additional_buy:,.0f}원이 "
                "추가 반영되었습니다."
            )

        elif (
            parsed[
                "additional_ratio"
            ] <= 0
            and parsed[
                "target_weight"
            ] > 0
        ):

            reasons.append(
                "현재는 추가매수 낙폭 조건이 "
                "발생하지 않았습니다."
            )

        if cash_scale_factor < 1.0:

            reasons.append(
                "계산상 남은 투자재원 범위에 맞춰 "
                "추천금액이 조정되었습니다."
            )

        result.reason = " ".join(
            reasons
        )

    # ---------------------------------------------------------
    # 9. 요약
    # ---------------------------------------------------------

    summary = {
        "initial_capital":
            initial_capital,

        "total_invested_so_far":
            total_invested_so_far,

        "remaining_cash":
            remaining_cash,

        "base_monthly_budget":
            remaining_base_budget,

        "max_additional_budget":
            max_additional_monthly,

        "additional_budget_used":
            additional_budget_used,

        "additional_budget_ratio":
            highest_additional_ratio,

        "additional_budget_allowed":
            allowed_additional_budget,

        "remaining_additional_buy":
            remaining_additional_budget,

        "additional_buy_triggered":
            additional_buy_triggered,

        "total_additional_buy":
            sum(
                result.additional_buy
                for result in results
            ),

        "total_recommended_buy":
            final_total_recommended,

        "total_portfolio_value_now":
            total_portfolio_value,

        "total_portfolio_value_expected":
            final_portfolio_value,

        "already_invested_in_cycle":
            already_invested_in_cycle,

        "cycle_desc":
            cycle_desc,
    }

    return {
        "summary": summary,
        "recommendations": results,
    }
