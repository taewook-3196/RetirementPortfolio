"""
scripts/test_yfinance_client.py

YFinanceClient 실제 가격 수집 테스트.

- AAPL 최근 가격을 Yahoo Finance에서 조회
- DB/Supabase에는 저장하지 않음
- 기존 prices 테이블 형식과 호환되는지 확인
"""

from __future__ import annotations

from data.yfinance_client import YFinanceClient


def main() -> None:
    ticker = "AAPL"
    days = 5

    print("=" * 60)
    print("Yahoo Finance 미국주식 가격 수집 테스트")
    print("=" * 60)

    client = YFinanceClient()

    asset_info = client.fetch_asset_info(
        ticker
    )

    print()
    print("미국 종목 정보")
    print(
        f"Ticker: {asset_info['ticker']}"
    )
    print(
        f"Name: {asset_info['name']}"
    )
    print(
        f"Market: {asset_info['market']}"
    )
    print(
        f"Exchange: {asset_info['exchange']}"
    )
    print(
        f"Asset type: {asset_info['asset_type']}"
    )
    print(
        f"Currency: {asset_info['currency']}"
    )

    assert asset_info["ticker"] == "AAPL"
    assert asset_info["market"] == "US"
    assert asset_info["currency"] == "USD"
    assert asset_info["asset_type"] == "STOCK"
    assert asset_info["name"]
    

    records = client.fetch_historical_prices(
        target_tickers=[ticker],
        days=days,
    )

    if not records:
        raise AssertionError(
            "AAPL 가격 데이터를 받지 못했습니다."
        )

    required_fields = {
        "date",
        "ticker",
        "name",
        "open_price",
        "high_price",
        "low_price",
        "close_price",
        "nav",
        "volume",
        "trading_value",
    }

    for record in records:
        missing_fields = (
            required_fields
            - set(record.keys())
        )

        if missing_fields:
            raise AssertionError(
                "필수 필드가 없습니다: "
                f"{sorted(missing_fields)}"
            )

        if record["ticker"] != ticker:
            raise AssertionError(
                "ticker가 올바르지 않습니다: "
                f"{record['ticker']}"
            )

        if float(
            record["close_price"]
        ) <= 0:
            raise AssertionError(
                "종가가 0 이하입니다."
            )

    latest = records[-1]

    print()
    print(
        f"수집 레코드: {len(records)}건"
    )
    print(
        f"최근 거래일: {latest['date']}"
    )
    print(
        f"Ticker: {latest['ticker']}"
    )
    print(
        f"가격: ${latest['close_price']:,.2f}"
    )
    print(
        f"거래량: {latest['volume']:,}"
    )

    print()
    print("=" * 60)
    print("YFINANCE TEST PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
