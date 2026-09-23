"""
strategy/recommendation.py

개인 퇴직연금/투자 포트폴리오 매수 의사결정 추천 엔진.

- 기본 매수금 배분
- 하락률 구간별 추가 매수금 산정
- 주기별 추가매수 한도 적용
- 전체 투자 가능 원금 한도 적용
- 목표비중 초과 종목 추가매수 제한
- 목표비중 0 이하 종목 매수 제외
- 매수 후 예상 비중 계산
- 추천 사유 생성
- 소수점 보유 수량 및 float 기반 금액 처리
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from strategy.allocation import (
    calculate_weight_gap,
    calculate_weight_gap_score,
)
from strategy.buy_signal import calculate_priority_score
from strategy.drawdown import (
    calculate_drawdown,
    calculate_drawdown_score,
    get_additional_buy_by_tier,
)


@dataclass
class ETFRecommendationInput:
    ticker: str
    name: str
    target_weight: float
    current_price: float
    recent_3m_high: float

    # 미국 주식 등의 소수점 보유 수량도 지원
    holding_quantity: float = 0.0

    # 현재 해당 종목의 평가금액
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
    추천 매수 금액을 1만원 단위로 반올림합니다.

    기존 추천 엔진의 동작을 유지하되
    내부 계산은 float 기반으로 처리합니다.
    """
    return float(
        round(
            float(amount),
            -4,
        )
    )


def generate_recommendations(
    inputs: List[ETFRecommendationInput],
    initial_capital: float = 100_000_000.0,
    base_monthly: float = 10_000_000.0,
    max_additional_monthly: float = 15_000_000.0,
    total_invested_so_far: float = 0.0,
    already_invested_in_cycle: bool = False,
    cycle_desc: str = "",
) -> Dict[str, Any]:
    """
    포트폴리오 데이터를 종합하여
    종목별 매수 추천 결과를 계산합니다.

    already_invested_in_cycle=True이면
    해당 주기에 이미 납입/매수한 것으로 보고
    추가 매수 추천을 제한합니다.
    """

    # -------------------------------------------------------------
    # 입력값 정규화
    # -------------------------------------------------------------

    initial_capital = max(
        0.0,
        float(initial_capital or 0),
    )

    base_monthly = max(
        0.0,
        float(base_monthly or 0),
    )

    max_additional_monthly = max(
        0.0,
        float(max_additional_monthly or 0),
    )

    total_invested_so_far = max(
        0.0,
        float(total_invested_so_far or 0),
    )

    remaining_cash = max(
        0.0,
        initial_capital - total_invested_so_far,
    )

    # -------------------------------------------------------------
    # 추천 대상이 없는 경우
    # -------------------------------------------------------------

    if not inputs:
        summary = {
            "initial_capital": initial_capital,
            "total_invested_so_far": total_invested_so_far,
            "remaining_cash": remaining_cash,
            "base_monthly_budget": base_monthly,
            "total_additional_buy": 0.0,
            "total_recommended_buy": 0.0,
            "total_portfolio_value_now": 0.0,
            "total_portfolio_value_expected": 0.0,
            "already_invested_in_cycle": already_invested_in_cycle,
            "cycle_desc": cycle_desc,
        }

        return {
            "summary": summary,
            "recommendations": [],
        }

    # -------------------------------------------------------------
    # 1. 현재 포트폴리오 총 평가액 및 비중 계산
    # -------------------------------------------------------------

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

    weights_map: Dict[str, float] = {}

    for item in inputs:
        current_asset_value = max(
            0.0,
            float(
                item.current_asset_value
                or 0
            ),
        )

        if total_portfolio_value > 0:
            weights_map[item.ticker] = (
                current_asset_value
                / total_portfolio_value
            )
        else:
            weights_map[item.ticker] = 0.0

    # -------------------------------------------------------------
    # 2. 낙폭, 비중 부족, 우선순위 및 추가매수 요구액 계산
    # -------------------------------------------------------------

    parsed_items: List[
        Dict[str, Any]
    ] = []

    total_requested_additional = 0.0

    for item in inputs:
        target_weight = float(
            item.target_weight or 0
        )

        current_price = float(
            item.current_price or 0
        )

        recent_high = float(
            item.recent_3m_high or 0
        )

        current_asset_value = max(
            0.0,
            float(
                item.current_asset_value
                or 0
            ),
        )

        current_weight = weights_map.get(
            item.ticker,
            0.0,
        )

        weight_gap = calculate_weight_gap(
            target_weight,
            current_weight,
        )

        drawdown = calculate_drawdown(
            current_price,
            recent_high,
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

        # 목표 비중이 없거나 초과한 종목,
        # 또는 이번 주기에 이미 매수한 경우
        # 추가매수를 하지 않습니다.
        if (
            target_weight <= 0
            or weight_gap <= 0
            or already_invested_in_cycle
        ):
            raw_additional = 0.0

        else:
            raw_additional = max(
                0.0,
                float(
                    get_additional_buy_by_tier(
                        drawdown
                    )
                    or 0
                ),
            )

        total_requested_additional += (
            raw_additional
        )

        parsed_items.append(
            {
                "item": item,
                "target_weight": target_weight,
                "current_price": current_price,
                "recent_high": recent_high,
                "current_asset_value": current_asset_value,
                "cur_weight": current_weight,
                "weight_gap": float(
                    weight_gap
                ),
                "drawdown": float(
                    drawdown
                ),
                "dd_score": int(
                    drawdown_score
                ),
                "wg_score": float(
                    weight_gap_score
                ),
                "priority_score": float(
                    priority_score
                ),
                "raw_additional": raw_additional,
            }
        )

    # -------------------------------------------------------------
    # 3. 주기별 추가매수 한도 적용
    # -------------------------------------------------------------

    effective_max_additional = (
        0.0
        if already_invested_in_cycle
        else max_additional_monthly
    )

    if (
        total_requested_additional
        > effective_max_additional
    ):
        total_priority_score = sum(
            max(
                0.0,
                float(
                    item[
                        "priority_score"
                    ]
                ),
            )
            for item in parsed_items
            if item["raw_additional"] > 0
        )

        for parsed in parsed_items:
            if (
                parsed["raw_additional"] > 0
                and total_priority_score > 0
                and effective_max_additional > 0
            ):
                ratio = (
                    max(
                        0.0,
                        parsed[
                            "priority_score"
                        ],
                    )
                    / total_priority_score
                )

                capped = (
                    effective_max_additional
                    * ratio
                )

                parsed[
                    "capped_additional"
                ] = _round_buy_amount(
                    capped
                )

            else:
                parsed[
                    "capped_additional"
                ] = 0.0

        # 반올림 때문에 총액이 한도를 초과할 수 있으므로
        # 초과분을 다시 비례 축소합니다.
        rounded_total = sum(
            parsed[
                "capped_additional"
            ]
            for parsed in parsed_items
        )

        if (
            rounded_total
            > effective_max_additional
            and rounded_total > 0
        ):
            scale = (
                effective_max_additional
                / rounded_total
            )

            for parsed in parsed_items:
                parsed[
                    "capped_additional"
                ] = (
                    _round_buy_amount(
                        parsed[
                            "capped_additional"
                        ]
                        * scale
                    )
                )

    else:
        for parsed in parsed_items:
            parsed[
                "capped_additional"
            ] = float(
                parsed[
                    "raw_additional"
                ]
            )

    # -------------------------------------------------------------
    # 4. 기본 매수금 배분
    # -------------------------------------------------------------

    for parsed in parsed_items:
        target_weight = parsed[
            "target_weight"
        ]

        # 목표 비중이 0 이하인 종목에는
        # 기본 매수금도 배정하지 않습니다.
        if target_weight <= 0:
            parsed[
                "base_buy"
            ] = 0.0

        else:
            parsed[
                "base_buy"
            ] = _round_buy_amount(
                base_monthly
                * target_weight
            )

    # -------------------------------------------------------------
    # 5. 전체 투자 가능 원금 한도 적용
    # -------------------------------------------------------------

    total_planned_buy = sum(
        float(
            parsed[
                "base_buy"
            ]
        )
        + float(
            parsed[
                "capped_additional"
            ]
        )
        for parsed in parsed_items
    )

    if (
        total_planned_buy > remaining_cash
        and total_planned_buy > 0
    ):
        cash_scale_factor = (
            remaining_cash
            / total_planned_buy
        )
    else:
        cash_scale_factor = 1.0

    # -------------------------------------------------------------
    # 6. 최종 추천 결과 생성
    # -------------------------------------------------------------

    results: List[
        ETFRecommendationResult
    ] = []

    final_total_recommended = 0.0

    for parsed in parsed_items:
        item: ETFRecommendationInput = (
            parsed["item"]
        )

        original_base = float(
            parsed["base_buy"]
        )

        original_additional = float(
            parsed[
                "capped_additional"
            ]
        )

        base_buy = _round_buy_amount(
            original_base
            * cash_scale_factor
        )

        additional_buy = (
            _round_buy_amount(
                original_additional
                * cash_scale_factor
            )
        )

        final_buy = (
            base_buy
            + additional_buy
        )

        # 반올림으로 인해 남은 현금을 초과하지 않도록
        # 마지막 단계에서 다시 제한합니다.
        available_for_this_item = max(
            0.0,
            remaining_cash
            - final_total_recommended,
        )

        if final_buy > available_for_this_item:
            final_buy = available_for_this_item

            if final_buy < base_buy:
                base_buy = final_buy
                additional_buy = 0.0
            else:
                additional_buy = max(
                    0.0,
                    final_buy - base_buy,
                )

        final_total_recommended += (
            final_buy
        )

        post_asset_value = (
            parsed[
                "current_asset_value"
            ]
            + final_buy
        )

        # 모든 종목의 최종 추천 금액이 결정되기 전에는
        # 정확한 최종 포트폴리오 총액을 알 수 없으므로
        # 우선 아래에서 결과를 만든 뒤 한 번 더 계산합니다.
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
                additional_buy=additional_buy,
                recommended_buy=final_buy,
                expected_weight_after=post_asset_value,
                reason="",
            )
        )

    # -------------------------------------------------------------
    # 7. 실제 최종 추천 총액 기준 예상 비중 및 사유 계산
    # -------------------------------------------------------------

    final_total_portfolio_post = (
        total_portfolio_value
        + final_total_recommended
    )

    for result, parsed in zip(
        results,
        parsed_items,
    ):
        item: ETFRecommendationInput = (
            parsed["item"]
        )

        post_asset_value = (
            parsed[
                "current_asset_value"
            ]
            + result.recommended_buy
        )

        if final_total_portfolio_post > 0:
            expected_weight = (
                post_asset_value
                / final_total_portfolio_post
            )
        else:
            expected_weight = (
                parsed[
                    "target_weight"
                ]
            )

        result.expected_weight_after = (
            expected_weight
        )

        reasons: List[str] = []

        weight_gap_pct = round(
            parsed[
                "weight_gap"
            ]
            * 100,
            1,
        )

        drawdown_pct = round(
            parsed[
                "drawdown"
            ]
            * 100,
            1,
        )

        current_weight_pct = round(
            parsed[
                "cur_weight"
            ]
            * 100,
            1,
        )

        target_weight_pct = round(
            parsed[
                "target_weight"
            ]
            * 100,
            1,
        )

        if parsed["target_weight"] <= 0:
            reasons.append(
                "목표 비중이 0%인 종목으로 "
                "정량 매수 추천에서 제외됩니다."
            )

        elif parsed["weight_gap"] <= 0:
            reasons.append(
                f"현재 비중({current_weight_pct}%)이 "
                f"목표 비중({target_weight_pct}%) 이상입니다."
            )

        elif already_invested_in_cycle:
            description = (
                cycle_desc
                if cycle_desc
                else "이번 주기"
            )

            reasons.append(
                f"목표 비중 대비 "
                f"{abs(weight_gap_pct)}%p 부족하지만, "
                f"{description}에 이미 매수 이력이 있어 "
                "추가 매수를 제한합니다."
            )

        else:
            reasons.append(
                f"목표 비중 대비 "
                f"{abs(weight_gap_pct)}%p 부족하며 "
                f"최근 3개월 고점 대비 "
                f"{abs(drawdown_pct)}% 하락했습니다."
            )

        if result.additional_buy > 0:
            reasons.append(
                "낙폭 구간에 따른 추가 매수금 "
                f"{result.additional_buy:,.0f}원이 "
                "반영되었습니다."
            )

        elif (
            parsed["raw_additional"] > 0
            and result.additional_buy == 0
            and cash_scale_factor < 1.0
        ):
            reasons.append(
                "남은 투자 가능 원금 한도로 인해 "
                "추가 매수가 제한되었습니다."
            )

        original_planned = (
            float(
                parsed[
                    "base_buy"
                ]
            )
            + float(
                parsed[
                    "capped_additional"
                ]
            )
        )

        if (
            cash_scale_factor < 1.0
            and result.recommended_buy
            < original_planned
        ):
            reasons.append(
                "남은 투자 가능 원금 "
                f"({remaining_cash:,.0f}원)에 맞추어 "
                "매수 금액이 조정되었습니다."
            )

        result.reason = " ".join(
            reasons
        )

    # -------------------------------------------------------------
    # 8. 요약
    # -------------------------------------------------------------

    summary = {
        "initial_capital": initial_capital,
        "total_invested_so_far": total_invested_so_far,
        "remaining_cash": remaining_cash,
        "base_monthly_budget": base_monthly,
        "total_additional_buy": sum(
            result.additional_buy
            for result in results
        ),
        "total_recommended_buy": (
            final_total_recommended
        ),
        "total_portfolio_value_now": (
            total_portfolio_value
        ),
        "total_portfolio_value_expected": (
            final_total_portfolio_post
        ),
        "already_invested_in_cycle": (
            already_invested_in_cycle
        ),
        "cycle_desc": cycle_desc,
    }

    return {
        "summary": summary,
        "recommendations": results,
    }
