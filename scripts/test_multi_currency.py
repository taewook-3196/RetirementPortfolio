"""
scripts/test_multi_currency.py

KRW/USD 혼합통화 포트폴리오 계산 검증용 테스트.

실제 DB, Supabase, 거래내역은 수정하지 않습니다.
portfolio.performance의 순수 계산 함수만 테스트합니다.

검증 항목:
1. KRW -> KRW 동일통화
2. USD -> USD 동일통화
3. USD -> KRW 환산
4. KRW -> USD 환산
5. 환율 없는 교차통화 계산 차단
6. KRW 계좌에 KRW + USD 종목이 함께 있을 때
   평가금액/손익/비중 계산의 기초가 되는 요약값 검증
"""

from __future__ import annotations

from portfolio.holdings import ETFPosition
from portfolio.performance import (
    calculate_portfolio_summary,
    convert_currency,
)


USD_KRW_RATE = 1350.0


def assert_close(
    actual: float,
    expected: float,
    tolerance: float = 0.01,
) -> None:
    if abs(actual - expected) > tolerance:
        raise AssertionError(
            f"예상값 {expected:,.2f}, "
            f"실제값 {actual:,.2f}"
        )


def test_same_currency() -> None:
    print("1. 동일통화 환산 테스트")

    krw = convert_currency(
        value=1_000_000,
        from_currency="KRW",
        to_currency="KRW",
    )

    usd = convert_currency(
        value=1_000,
        from_currency="USD",
        to_currency="USD",
    )

    assert_close(
        krw,
        1_000_000,
    )

    assert_close(
        usd,
        1_000,
    )

    print("   PASS")


def test_cross_currency() -> None:
    print("2. KRW/USD 교차환산 테스트")

    usd_to_krw = convert_currency(
        value=1_000,
        from_currency="USD",
        to_currency="KRW",
        usd_krw_rate=USD_KRW_RATE,
    )

    assert_close(
        usd_to_krw,
        1_350_000,
    )

    krw_to_usd = convert_currency(
        value=1_350_000,
        from_currency="KRW",
        to_currency="USD",
        usd_krw_rate=USD_KRW_RATE,
    )

    assert_close(
        krw_to_usd,
        1_000,
    )

    print("   PASS")


def test_missing_fx_rate() -> None:
    print("3. 환율 누락 안전장치 테스트")

    try:
        convert_currency(
            value=1_000,
            from_currency="USD",
            to_currency="KRW",
        )

    except ValueError:
        print("   PASS")
        return

    raise AssertionError(
        "환율 없이 USD -> KRW 환산이 허용되었습니다."
    )


def build_krw_position() -> ETFPosition:
    """
    KRW 종목 예시.

    매수원가: 5,000,000원
    평가금액: 5,500,000원
    평가손익: +500,000원
    """

    return ETFPosition(
        ticker="KR_TEST",
        name="KRW 테스트 종목",
        currency="KRW",
        quantity=100,
        total_buy_cost=5_000_000,
        average_buy_price=50_000,
        current_price=55_000,
        current_value=5_500_000,
        unrealized_pnl=500_000,
        unrealized_roi=0.10,
        realized_pnl=0,
        total_dividends=0,
        total_pnl=500_000,
        total_fees=0,
    )


def build_usd_position() -> ETFPosition:
    """
    USD 종목 예시.

    매수원가: $3,000
    평가금액: $4,000
    평가손익: +$1,000

    환율 1,350원 기준:
    매수원가 = 4,050,000원
    평가금액 = 5,400,000원
    평가손익 = 1,350,000원
    """

    return ETFPosition(
        ticker="US_TEST",
        name="USD 테스트 종목",
        currency="USD",
        quantity=20,
        total_buy_cost=3_000,
        average_buy_price=150,
        current_price=200,
        current_value=4_000,
        unrealized_pnl=1_000,
        unrealized_roi=1_000 / 3_000,
        realized_pnl=0,
        total_dividends=0,
        total_pnl=1_000,
        total_fees=0,
    )


def test_mixed_currency_krw_account() -> None:
    print("4. KRW 계좌 + KRW/USD 혼합종목 테스트")

    positions = {
        "KR_TEST": build_krw_position(),
        "US_TEST": build_usd_position(),
    }

    summary = calculate_portfolio_summary(
        positions=positions,
        initial_capital=20_000_000,
        base_currency="KRW",
        usd_krw_rate=USD_KRW_RATE,
    )

    # KRW 종목 매수원가
    # 5,000,000
    #
    # USD 종목 매수원가
    # $3,000 × 1,350 = 4,050,000
    #
    # 합계
    # 9,050,000
    expected_invested = 9_050_000

    # KRW 종목 평가액
    # 5,500,000
    #
    # USD 종목 평가액
    # $4,000 × 1,350 = 5,400,000
    #
    # 합계
    # 10,900,000
    expected_current_value = 10_900_000

    # 평가손익
    # 500,000
    # + $1,000 × 1,350
    # = 1,850,000
    expected_unrealized_pnl = 1_850_000

    expected_total_pnl = 1_850_000

    expected_roi = (
        expected_total_pnl
        / expected_invested
    )

    expected_remaining_cash = (
        20_000_000
        - expected_invested
    )

    assert summary.currency == "KRW"

    assert_close(
        summary.total_invested,
        expected_invested,
    )

    assert_close(
        summary.total_current_value,
        expected_current_value,
    )

    assert_close(
        summary.total_unrealized_pnl,
        expected_unrealized_pnl,
    )

    assert_close(
        summary.total_pnl,
        expected_total_pnl,
    )

    assert_close(
        summary.total_roi,
        expected_roi,
        tolerance=0.000001,
    )

    assert_close(
        summary.remaining_cash,
        expected_remaining_cash,
    )

    assert summary.position_count == 2

    print("   PASS")

    print()
    print("   계산 결과")
    print(
        f"   투자원금: "
        f"{summary.total_invested:,.0f} KRW"
    )
    print(
        f"   평가금액: "
        f"{summary.total_current_value:,.0f} KRW"
    )
    print(
        f"   평가손익: "
        f"{summary.total_unrealized_pnl:,.0f} KRW"
    )
    print(
        f"   총수익률: "
        f"{summary.total_roi * 100:.2f}%"
    )
    print(
        f"   잔여금액: "
        f"{summary.remaining_cash:,.0f} KRW"
    )


def test_mixed_currency_without_fx() -> None:
    print()
    print("5. 혼합통화 + 환율 누락 차단 테스트")

    positions = {
        "KR_TEST": build_krw_position(),
        "US_TEST": build_usd_position(),
    }

    try:
        calculate_portfolio_summary(
            positions=positions,
            initial_capital=20_000_000,
            base_currency="KRW",
        )

    except ValueError:
        print("   PASS")
        return

    raise AssertionError(
        "혼합통화 포트폴리오가 "
        "환율 없이 계산되었습니다."
    )


def main() -> None:
    print("=" * 60)
    print("혼합통화 포트폴리오 계산 테스트")
    print("=" * 60)
    print(
        f"테스트 USD/KRW 환율: "
        f"{USD_KRW_RATE:,.2f}"
    )
    print()

    test_same_currency()
    test_cross_currency()
    test_missing_fx_rate()
    test_mixed_currency_krw_account()
    test_mixed_currency_without_fx()

    print()
    print("=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
