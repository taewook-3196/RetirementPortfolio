"""
data/yfinance_client.py

Yahoo Finance 데이터를 이용한 미국 주식/ETF 가격 수집기.

- 미국 주식 및 ETF의 최근 일별 OHLCV 수집
- 기존 prices 테이블과 동일한 레코드 형식으로 반환
- DB 저장은 수행하지 않음
- API 키 불필요

주의:
- 이 모듈은 가격 수집만 담당합니다.
- 종목의 시장/통화 판별은 price_updater.py에서 수행합니다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List


logger = logging.getLogger(
    "RetirementPortfolio.YFinanceClient"
)


class YFinanceClient:
    """Yahoo Finance 기반 미국 주식/ETF 가격 클라이언트."""

    def fetch_historical_prices(
        self,
        target_tickers: List[str],
        days: int = 90,
    ) -> List[Dict[str, Any]]:
        """
        대상 종목들의 최근 N일 일별 가격을 수집합니다.

        반환 형식:
        [
            {
                "date": "YYYYMMDD",
                "ticker": str,
                "name": str,
                "open_price": float,
                "high_price": float,
                "low_price": float,
                "close_price": float,
                "nav": float,
                "volume": int,
                "trading_value": float,
            }
        ]
        """

        try:
            import yfinance as yf

        except ImportError as exc:
            raise RuntimeError(
                "yfinance가 설치되어 있지 않습니다. "
                "requirements.txt에 yfinance를 추가해야 합니다."
            ) from exc

        all_records: List[
            Dict[str, Any]
        ] = []

        clean_tickers = []

        for ticker in target_tickers:
            clean_ticker = (
                str(ticker or "")
                .strip()
                .upper()
            )

            if (
                clean_ticker
                and clean_ticker
                not in clean_tickers
            ):
                clean_tickers.append(
                    clean_ticker
                )

        if not clean_tickers:
            return all_records

        # 영업일뿐 아니라 주말/휴장일을 고려하여
        # 요청 일수보다 넉넉한 달력 기간을 조회합니다.
        calendar_days = max(
            int(days * 1.7),
            days + 14,
        )

        end_date = (
            datetime.now()
            + timedelta(days=1)
        )

        start_date = (
            end_date
            - timedelta(
                days=calendar_days
            )
        )

        for ticker in clean_tickers:

            try:
                yf_ticker = yf.Ticker(
                    ticker
                )

                # 종목명은 실패해도 가격 수집에
                # 영향을 주지 않도록 ticker를 fallback으로 사용합니다.
                name = ticker

                try:
                    info = (
                        yf_ticker.fast_info
                    )

                    # fast_info에는 종목명이 없는 경우가 많으므로
                    # 가격 수집 자체에는 의존하지 않습니다.
                    if info is None:
                        logger.debug(
                            "Yahoo Finance fast_info 없음: %s",
                            ticker,
                        )

                except Exception:
                    pass

                history = (
                    yf_ticker.history(
                        start=(
                            start_date.strftime(
                                "%Y-%m-%d"
                            )
                        ),
                        end=(
                            end_date.strftime(
                                "%Y-%m-%d"
                            )
                        ),
                        interval="1d",
                        auto_adjust=False,
                        actions=False,
                    )
                )

                if (
                    history is None
                    or history.empty
                ):
                    logger.warning(
                        "Yahoo Finance 가격 데이터 없음: %s",
                        ticker,
                    )
                    continue

                # 최근 days개의 실제 거래일만 사용합니다.
                history = history.tail(
                    days
                )

                count = 0

                for index, row in (
                    history.iterrows()
                ):
                    try:
                        open_price = float(
                            row.get(
                                "Open",
                                0,
                            )
                            or 0
                        )

                        high_price = float(
                            row.get(
                                "High",
                                0,
                            )
                            or 0
                        )

                        low_price = float(
                            row.get(
                                "Low",
                                0,
                            )
                            or 0
                        )

                        close_price = float(
                            row.get(
                                "Close",
                                0,
                            )
                            or 0
                        )

                        volume_value = row.get(
                            "Volume",
                            0,
                        )

                        if close_price <= 0:
                            continue

                        if open_price <= 0:
                            open_price = (
                                close_price
                            )

                        if high_price <= 0:
                            high_price = max(
                                open_price,
                                close_price,
                            )

                        if low_price <= 0:
                            low_price = min(
                                open_price,
                                close_price,
                            )

                        try:
                            volume = int(
                                float(
                                    volume_value
                                    or 0
                                )
                            )
                        except (
                            TypeError,
                            ValueError,
                        ):
                            volume = 0

                        date_str = (
                            index.strftime(
                                "%Y%m%d"
                            )
                        )

                        all_records.append(
                            {
                                "date":
                                    date_str,

                                "ticker":
                                    ticker,

                                "name":
                                    name,

                                "open_price":
                                    open_price,

                                "high_price":
                                    high_price,

                                "low_price":
                                    low_price,

                                "close_price":
                                    close_price,

                                # 일반 주식에는 ETF NAV와 같은
                                # 별도 값이 없으므로 기존 스키마
                                # 호환을 위해 종가를 사용합니다.
                                "nav":
                                    close_price,

                                "volume":
                                    volume,

                                "trading_value":
                                    0.0,
                            }
                        )

                        count += 1

                    except Exception as exc:
                        logger.debug(
                            "Yahoo Finance %s 개별 가격행 처리 실패: %s",
                            ticker,
                            exc,
                        )

                logger.info(
                    "Yahoo Finance: %s 시세 %d건 수집 완료",
                    ticker,
                    count,
                )

            except Exception as exc:
                logger.warning(
                    "Yahoo Finance (%s) 시세 수집 중 오류: %s",
                    ticker,
                    exc,
                )

        return all_records
