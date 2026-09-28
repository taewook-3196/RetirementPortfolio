"""
scripts/test_price_updater_routing.py

price_updater의 KR/US 시장 라우팅 테스트.

목적:
- KR 종목은 KRX 경로로 전달되는지 확인
- US/USD 종목은 Yahoo Finance 경로로 전달되는지 확인
- 미국 종목이 KRX로 전달되지 않는지 확인
- 국내 종목이 Yahoo Finance로 전달되지 않는지 확인
- 실제 Supabase/외부 API는 사용하지 않음
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from data.price_updater import update_market_prices


KR_TICKER = "069500"
US_TICKER = "AAPL"


class FakeRepository:
    """
    실제 DB를 사용하지 않는 테스트용 Repository.
    """

    def __init__(self):
        self.user_id = "test-user"

        self.saved_master = []
        self.saved_prices = []

        self.assets = {
            KR_TICKER: SimpleNamespace(
                ticker=KR_TICKER,
                name="KODEX 200",
                market="KR",
                exchange="KRX",
                asset_type="ETF",
                currency="KRW",
            ),
            US_TICKER: SimpleNamespace(
                ticker=US_TICKER,
                name="Apple Inc.",
                market="US",
                exchange="NASDAQ",
                asset_type="STOCK",
                currency="USD",
            ),
        }

    def get_account_targets(
        self,
        account_id=None,
    ):
        return []

    def get_transactions(self):
        return [
            SimpleNamespace(
                ticker=US_TICKER,
            )
        ]

    def get_etf_master(
        self,
        ticker,
    ):
        return self.assets.get(
            str(ticker).strip().upper()
        )

    def save_etf_master(
        self,
        items,
    ):
        self.saved_master.extend(
            items
        )

        for item in items:
            if isinstance(item, dict):
                ticker = (
                    str(
                        item.get(
                            "ticker",
                            "",
                        )
                    )
                    .strip()
                    .upper()
                )

                if ticker:
                    self.assets[ticker] = (
                        SimpleNamespace(
                            **item
                        )
                    )

        return len(items)

    def upsert_prices(
        self,
        records,
    ):
        self.saved_prices.extend(
            records
        )

        return len(records)


class FakeKRXClient:
    """
    실제 KRX API를 호출하지 않는 테스트용 클라이언트.
    """

    received_tickers = []

    def __init__(self):
        self.last_etf_master = []

    def is_configured(self):
        return True

    def fetch_historical_prices(
        self,
        target_tickers,
        days=90,
    ):
        type(self).received_tickers = list(
            target_tickers
        )

        return [
            {
                "date": "20260925",
                "ticker": KR_TICKER,
                "name": "KODEX 200",
                "open_price": 50000.0,
                "high_price": 51000.0,
                "low_price": 49500.0,
                "close_price": 50500.0,
                "nav": 50500.0,
                "volume": 1000,
                "trading_value": 0.0,
            }
        ]


class FakeYFinanceClient:
    """
    실제 Yahoo Finance를 호출하지 않는 테스트용 클라이언트.
    """

    received_tickers = []

    def fetch_historical_prices(
        self,
        target_tickers,
        days=90,
    ):
        type(self).received_tickers = list(
            target_tickers
        )

        return [
            {
                "date": "20260925",
                "ticker": US_TICKER,
                "name": "Apple Inc.",
                "open_price": 250.0,
                "high_price": 255.0,
                "low_price": 248.0,
                "close_price": 252.0,
                "nav": 252.0,
                "volume": 1000000,
                "trading_value": 0.0,
            }
        ]


def build_test_config():
    """
    실제 config 파일 대신 사용할 최소 설정.
    """

    return SimpleNamespace(
        data_source="krx",

        # 069500은 price_updater 자체에서도
        # 대표 ETF로 추가되므로 비워도 됩니다.
        etfs=[],

        watchlist=[],
    )


def main():
    print("=" * 60)
    print("Price Updater KR/US Routing Test")
    print("=" * 60)

    repository = FakeRepository()
    config = build_test_config()

    FakeKRXClient.received_tickers = []
    FakeYFinanceClient.received_tickers = []

    with (
        patch(
            "data.price_updater.KRXClient",
            FakeKRXClient,
        ),
        patch(
            "data.price_updater.YFinanceClient",
            FakeYFinanceClient,
        ),
    ):
        result = update_market_prices(
            config=config,
            repo=repository,
            user_id=repository.user_id,
            days=5,
        )

    print()
    print(
        "KRX 전달 종목:",
        FakeKRXClient.received_tickers,
    )

    print(
        "Yahoo 전달 종목:",
        FakeYFinanceClient.received_tickers,
    )

    print(
        "저장 가격 ticker:",
        [
            item["ticker"]
            for item
            in repository.saved_prices
        ],
    )

    print(
        "실행 결과:",
        result,
    )

    # ---------------------------------------------------------
    # 1. KR 종목은 KRX에 전달되어야 함
    # ---------------------------------------------------------
    assert (
        KR_TICKER
        in FakeKRXClient.received_tickers
    ), (
        f"{KR_TICKER}이 "
        "KRX에 전달되지 않았습니다."
    )

    # ---------------------------------------------------------
    # 2. US 종목은 KRX에 전달되면 안 됨
    # ---------------------------------------------------------
    assert (
        US_TICKER
        not in FakeKRXClient.received_tickers
    ), (
        f"{US_TICKER}이 "
        "잘못 KRX에 전달되었습니다."
    )

    # ---------------------------------------------------------
    # 3. US 종목은 Yahoo에 전달되어야 함
    # ---------------------------------------------------------
    assert (
        US_TICKER
        in FakeYFinanceClient.received_tickers
    ), (
        f"{US_TICKER}이 "
        "Yahoo Finance에 전달되지 않았습니다."
    )

    # ---------------------------------------------------------
    # 4. KR 종목은 Yahoo에 전달되면 안 됨
    # ---------------------------------------------------------
    assert (
        KR_TICKER
        not in FakeYFinanceClient.received_tickers
    ), (
        f"{KR_TICKER}이 "
        "잘못 Yahoo Finance에 전달되었습니다."
    )

    # ---------------------------------------------------------
    # 5. 두 시장 가격 모두 저장 대상으로 합쳐져야 함
    # ---------------------------------------------------------
    saved_tickers = {
        item["ticker"]
        for item
        in repository.saved_prices
    }

    assert KR_TICKER in saved_tickers
    assert US_TICKER in saved_tickers

    # ---------------------------------------------------------
    # 6. 결과에서도 KR/US 종목 수가 확인되어야 함
    # ---------------------------------------------------------
    assert result["status"] == "success"
    assert result["kr_tickers"] == 1
    assert result["us_tickers"] == 1
    assert result["saved_count"] == 2

    print()
    print("=" * 60)
    print("PRICE UPDATER ROUTING TEST PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
