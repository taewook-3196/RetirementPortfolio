"""
portfolio/performance.py

전체 포트폴리오 성과 요약 및 지표 계산 모듈.

- 종목별 원래 통화 금액을 기준 통화로 환산
- 총 투자원금
- 현재 평가금액
- 평가손익 및 실현손익
- 누적 분배금/배당금
- 총 손익 및 총 수익률
- 남은 투자 가능 금액
- 현재 보유 종목 수

주의:
- ETFPosition 내부 금액은 종목의 원래 통화 기준입니다.
- 이 모듈에서는 합산할 때만 기준 통화로 환산합니다.
- 서로 다른 통화 간 환산이 필요한데 유효한 환율이 없으면
  계산을 중단하여 잘못된 금액이 조용히 사용되지 않도록 합니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from portfolio.holdings import ETFPosition


@dataclass
class PortfolioSummary:
    # 요약 금액의 기준 통화
    currency: str

    # 설정된 초기 총 투자금 한도
    initial_capital: float

    # 현재 보유분의 총 매수원가
    total_invested: float

    # 현재 총 평가금액
    total_current_value: float

    # 총 평가손익
    total_unrealized_pnl: float

    # 총 실현손익
    total_realized_pnl: float

    # 총 누적 분배금/배당금
    total_dividends: float

    # 평가손익 + 실현손익 + 분배금/배당금
    total_pnl: float

    # 총 손익 / 현재 보유분 총 매수원가
    total_roi: float

    # 초기 투자 한도 - 현재 보유분 총 매수원가
    remaining_cash: float

    # 현재 수량이 0보다 큰 종목 수
    position_count: int


def convert_currency(
    value: float,
    from_currency: str,
    to_currency: str,
    usd_krw_rate: Optional[float] = None,
) -> float:
    """
    금액을 지정된 통화로 환산합니다.

    현재 지원:
    - KRW -> KRW
    - USD -> USD
    - USD -> KRW
    - KRW -> USD

    usd_krw_rate:
        1 USD당 KRW 금액.
        예: 1350.0

    같은 통화끼리는 환율이 없어도 그대로 반환합니다.

    서로 다른 KRW/USD 통화 간 환산에는 반드시
    유효한 USD/KRW 환율이 필요합니다.

    지원하지 않는 통화 조합 또는 유효하지 않은 환율은
    오류를 발생시켜 잘못된 금액을 조용히 계산하지
    않도록 합니다.
    """

    amount = float(
        value or 0
    )

    source = str(
        from_currency or "KRW"
    ).strip().upper()

    target = str(
        to_currency or "KRW"
    ).strip().upper()

    # 같은 통화끼리는 환율이 필요하지 않습니다.
    if source == target:
        return amount

    # 현재 시스템에서 지원하는 교차통화는
    # KRW와 USD 사이뿐입니다.
    supported_cross_pairs = {
        ("USD", "KRW"),
        ("KRW", "USD"),
    }

    if (
        source,
        target,
    ) not in supported_cross_pairs:
        raise ValueError(
            "지원하지 않는 통화 환산입니다: "
            f"{source} -> {target}"
        )

    # 서로 다른 통화 간 환산에서만
    # 환율을 검사합니다.
    if usd_krw_rate is None:
        raise ValueError(
            "USD/KRW 환율이 없습니다. "
            f"{source} -> {target} "
            "환산을 수행할 수 없습니다."
        )

    try:
        rate = float(
            usd_krw_rate
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise ValueError(
            "USD/KRW 환율이 올바른 숫자가 아닙니다."
        ) from exc

    if rate <= 0:
        raise ValueError(
            "USD/KRW 환율은 0보다 커야 합니다."
        )

    if (
        source == "USD"
        and target == "KRW"
    ):
        return amount * rate

    if (
        source == "KRW"
        and target == "USD"
    ):
        return amount / rate

    # 위 supported_cross_pairs 검증 때문에
    # 정상적으로는 도달하지 않는 안전장치입니다.
    raise ValueError(
        "지원하지 않는 통화 환산입니다: "
        f"{source} -> {target}"
    )


def calculate_portfolio_summary(
    positions: Dict[str, ETFPosition],
    initial_capital: float = 100_000_000.0,
    base_currency: str = "KRW",
    usd_krw_rate: Optional[float] = None,
) -> PortfolioSummary:
    """
    모든 종목의 포지션을 기준 통화로 환산한 뒤
    포트폴리오 성과 요약을 계산합니다.

    예:
        KRW 계좌 안에 USD 종목이 있는 경우
        USD 금액을 USD/KRW 환율로 KRW 환산한 뒤
        계좌 합계에 포함합니다.

    같은 통화만 존재하는 계좌:
        USD/KRW 환율이 없어도 계산할 수 있습니다.

        예:
        - KRW 계좌 + KRW 종목
        - USD 계좌 + USD 종목

    혼합통화 계좌:
        서로 다른 통화 간 환산이 필요하므로
        유효한 USD/KRW 환율이 반드시 필요합니다.

    주의:
        현재 시스템에는 거래 당시 환율/실제 결제금액이
        별도로 저장되어 있지 않습니다.

        따라서 외화 종목의 과거 매수원가와 실현손익 등을
        기준 통화로 환산할 때도 전달받은 현재 환율을
        사용합니다.

        이는 혼합 통화 자산의 합산을 가능하게 하기 위한
        현재 단계의 계산 방식이며,
        실제 환전손익까지 포함한 정확한 계좌 수익률 계산은
        향후 거래별 환율 또는 결제금액 저장이 필요합니다.
    """

    capital = float(
        initial_capital or 0
    )

    summary_currency = str(
        base_currency or "KRW"
    ).strip().upper()

    def converted(
        value: float,
        position: ETFPosition,
    ) -> float:
        position_currency = str(
            position.currency
            or summary_currency
        ).strip().upper()

        return convert_currency(
            value=value,
            from_currency=position_currency,
            to_currency=summary_currency,
            usd_krw_rate=usd_krw_rate,
        )

    total_invested = sum(
        converted(
            position.total_buy_cost,
            position,
        )
        for position in positions.values()
    )

    total_current_value = sum(
        converted(
            position.current_value,
            position,
        )
        for position in positions.values()
    )

    total_unrealized_pnl = sum(
        converted(
            position.unrealized_pnl,
            position,
        )
        for position in positions.values()
    )

    total_realized_pnl = sum(
        converted(
            position.realized_pnl,
            position,
        )
        for position in positions.values()
    )

    total_dividends = sum(
        converted(
            position.total_dividends,
            position,
        )
        for position in positions.values()
    )

    total_pnl = (
        total_unrealized_pnl
        + total_realized_pnl
        + total_dividends
    )

    if total_invested > 0:
        total_roi = (
            total_pnl
            / total_invested
        )
    else:
        total_roi = 0.0

    remaining_cash = max(
        0.0,
        capital - total_invested,
    )

    active_positions = sum(
        1
        for position in positions.values()
        if float(
            position.quantity or 0
        ) > 0
    )

    return PortfolioSummary(
        currency=summary_currency,

        initial_capital=round(
            capital,
            2,
        ),

        total_invested=round(
            total_invested,
            2,
        ),

        total_current_value=round(
            total_current_value,
            2,
        ),

        total_unrealized_pnl=round(
            total_unrealized_pnl,
            2,
        ),

        total_realized_pnl=round(
            total_realized_pnl,
            2,
        ),

        total_dividends=round(
            total_dividends,
            2,
        ),

        total_pnl=round(
            total_pnl,
            2,
        ),

        total_roi=round(
            total_roi,
            6,
        ),

        remaining_cash=round(
            remaining_cash,
            2,
        ),

        position_count=active_positions,
    )
