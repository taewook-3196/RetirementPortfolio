"""
data/price_updater.py

시장 가격 데이터를 수집하고 PostgreSQL/Supabase DB에 저장/갱신하는 모듈.

지원 시장:
- 한국(KR): KRX 공식 Open API 우선, 누락/실패 시 네이버 금융
- 미국(US): Yahoo Finance(yfinance)

주요 기능:
- asset_master의 market/currency 정보를 기준으로 데이터 공급자 선택
- 사용자별 계좌 목표 종목 및 실제 거래 종목을 수집 대상에 포함
- 가격 저장 전에 asset_master 종목 정보 보장
- 국내/미국 가격을 공통 prices 테이블 형식으로 저장
- CLI 및 GitHub Actions 실행 지원
"""

from __future__ import annotations

import logging
import math
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.config import AppConfig, load_config
from core.logging_config import setup_logging
from core.paths import ensure_directories
from database.repository import Repository
from data.krx_client import KRXClient
from data.yfinance_client import YFinanceClient


logger = logging.getLogger(
    "RetirementPortfolio.PriceUpdater"
)


def update_market_prices(
    config: Optional[AppConfig] = None,
    repo: Optional[Repository] = None,
    user_id: Optional[str] = None,
    days: int = 90,
    scenario: str = "normal",
    **kwargs,
) -> Dict[str, Any]:
    """
    설정 및 사용자 포트폴리오에 포함된 종목의 가격 데이터를 수집하여
    PostgreSQL/Supabase DB에 저장합니다.

    시장 구분:
    - KR: KRX -> Naver fallback
    - US: Yahoo Finance

    user_id가 있으면 해당 사용자의 계좌 목표 종목과 실제 거래 종목도
    가격 수집 대상에 포함합니다.
    """
    ensure_directories()

    cfg = config or load_config()
    repository = repo or Repository(
        user_id=user_id
    )

    seen_tickers = set()
    target_tickers: List[str] = []

    asset_info: Dict[
        str,
        Dict[str, str],
    ] = {}

    def add_target(
        ticker: str,
        name: str,
        market: str = "KR",
        exchange: str = "KRX",
        asset_type: str = "ETF",
        currency: str = "KRW",
    ) -> None:
        """
        가격 수집 대상 종목을 중복 없이 추가하고
        asset_master 저장에 필요한 정보도 준비합니다.

        시장 판별은 ticker 모양이 아니라
        asset_master의 market/currency 정보를 우선합니다.
        """
        clean_market = (
            str(market or "KR")
            .strip()
            .upper()
        )

        clean_currency = (
            str(currency or "KRW")
            .strip()
            .upper()
        )

        clean_exchange = (
            str(exchange or "")
            .strip()
            .upper()
        )

        clean_asset_type = (
            str(asset_type or "STOCK")
            .strip()
            .upper()
        )

        clean_ticker = (
            str(ticker or "")
            .strip()
            .upper()
        )

        if not clean_ticker:
            return

        # 국내 숫자 종목코드만 6자리로 정규화합니다.
        # AAPL, MSFT 같은 미국 ticker에는 적용하지 않습니다.
        if (
            clean_market == "KR"
            and clean_ticker.isdigit()
        ):
            clean_ticker = (
                clean_ticker.zfill(6)
            )

        clean_name = (
            str(name or clean_ticker)
            .strip()
        )

        if not clean_exchange:
            if clean_market == "KR":
                clean_exchange = "KRX"
            elif clean_market == "US":
                clean_exchange = "US"

        if clean_ticker not in seen_tickers:
            seen_tickers.add(
                clean_ticker
            )
            target_tickers.append(
                clean_ticker
            )

        asset_info[clean_ticker] = {
            "ticker": clean_ticker,
            "name": clean_name,
            "market": clean_market,
            "exchange": clean_exchange,
            "asset_type": clean_asset_type,
            "currency": clean_currency,
        }

    # -------------------------------------------------------------
    # 1. 기본 설정 종목
    # -------------------------------------------------------------
    for etf in cfg.etfs:
        add_target(
            ticker=etf.ticker,
            name=etf.name,
            market="KR",
            exchange="KRX",
            asset_type="ETF",
            currency="KRW",
        )

    # -------------------------------------------------------------
    # 2. 기본 관심종목
    # -------------------------------------------------------------
    for watch in getattr(
        cfg,
        "watchlist",
        [],
    ):
        add_target(
            ticker=watch.ticker,
            name=watch.name,
            market="KR",
            exchange="KRX",
            asset_type="ETF",
            currency="KRW",
        )

    # -------------------------------------------------------------
    # 3. 현재 사용자의 계좌 목표 종목 및 실제 거래 종목
    # -------------------------------------------------------------
    if repository.user_id:
        for target in (
            repository.get_account_targets(
                account_id=None
            )
        ):
            master = (
                repository.get_etf_master(
                    target.ticker
                )
            )

            if master:
                add_target(
                    ticker=master.ticker,
                    name=master.name,
                    market=master.market,
                    exchange=(
                        master.exchange
                        or (
                            "KRX"
                            if str(
                                master.market
                                or ""
                            ).upper() == "KR"
                            else "US"
                        )
                    ),
                    asset_type=(
                        master.asset_type
                    ),
                    currency=(
                        master.currency
                    ),
                )
            else:
                # 자산 마스터가 없는 기존 종목은
                # 현재 시스템의 기존 동작과 호환되도록
                # 국내 종목으로 처리합니다.
                add_target(
                    ticker=target.ticker,
                    name=target.name,
                    market="KR",
                    exchange="KRX",
                    asset_type="ETF",
                    currency="KRW",
                )

        for tx in (
            repository.get_transactions()
        ):
            master = (
                repository.get_etf_master(
                    tx.ticker
                )
            )

            if master:
                add_target(
                    ticker=master.ticker,
                    name=master.name,
                    market=master.market,
                    exchange=(
                        master.exchange
                        or (
                            "KRX"
                            if str(
                                master.market
                                or ""
                            ).upper() == "KR"
                            else "US"
                        )
                    ),
                    asset_type=(
                        master.asset_type
                    ),
                    currency=(
                        master.currency
                    ),
                )
            else:
                # ticker 문자열만 보고 미국 종목이라고
                # 추측하지 않습니다.
                add_target(
                    ticker=tx.ticker,
                    name=tx.ticker,
                    market="KR",
                    exchange="KRX",
                    asset_type="ETF",
                    currency="KRW",
                )

    # -------------------------------------------------------------
    # 4. 모닝 리포트 국내 시장 대표 ETF 보장
    # -------------------------------------------------------------
    add_target(
        ticker="069500",
        name="KODEX 200",
        market="KR",
        exchange="KRX",
        asset_type="ETF",
        currency="KRW",
    )

    # 가격 저장 전에 자산 마스터를 보장합니다.
    repository.save_etf_master(
        list(asset_info.values())
    )

    # -------------------------------------------------------------
    # 5. 시장별 수집 대상 분리
    # -------------------------------------------------------------
    kr_tickers: List[str] = []
    us_tickers: List[str] = []

    for ticker in target_tickers:
        info = asset_info.get(
            ticker,
            {},
        )

        market = (
            str(
                info.get(
                    "market",
                    "KR",
                )
            )
            .strip()
            .upper()
        )

        currency = (
            str(
                info.get(
                    "currency",
                    "KRW",
                )
            )
            .strip()
            .upper()
        )

        if (
            market == "US"
            or currency == "USD"
        ):
            us_tickers.append(
                ticker
            )
        else:
            kr_tickers.append(
                ticker
            )

    logger.info(
        "가격 수집 대상 분리 완료: "
        "KR %d종목, US %d종목",
        len(kr_tickers),
        len(us_tickers),
    )

    configured_source = (
        str(cfg.data_source)
        .strip()
        .lower()
    )

    records: List[
        Dict[str, Any]
    ] = []

    sources_used: List[str] = []

    # -------------------------------------------------------------
    # 6. Mock 데이터
    # -------------------------------------------------------------
    if configured_source == "mock":
        from data.mock_provider import (
            MockDataProvider,
        )

        mock_provider = (
            MockDataProvider(
                scenario=scenario
            )
        )

        records = (
            mock_provider
            .get_historical_prices(
                list(
                    asset_info.values()
                ),
                days=days,
            )
        )

        sources_used.append("mock")

        logger.info(
            "MockDataProvider 데이터 생성 완료 "
            "(시나리오: %s, 종목: %s)",
            scenario,
            target_tickers,
        )

    else:
        # ---------------------------------------------------------
        # 7. 국내 가격 수집
        # ---------------------------------------------------------
        if kr_tickers:
            kr_records: List[
                Dict[str, Any]
            ] = []

            kr_source = (
                configured_source
            )

            # 기존 real 설정은 네이버 금융을 사용합니다.
            if kr_source == "real":
                kr_source = "naver"

            # 알 수 없는 설정값은 기존 서비스의
            # 기본 방향에 맞춰 KRX를 우선 사용합니다.
            if kr_source not in {
                "krx",
                "naver",
            }:
                kr_source = "krx"

            # -----------------------------------------------------
            # 7-1. KRX 공식 Open API
            # -----------------------------------------------------
            if kr_source == "krx":
                try:
                    client = KRXClient()

                    if client.is_configured():
                        logger.info(
                            "KRX 공식 Open API 가격 데이터 "
                            "수집 시작 (종목: %s)",
                            kr_tickers,
                        )

                        kr_records = (
                            client
                            .fetch_historical_prices(
                                kr_tickers,
                                days=days,
                            )
                        )

                        logger.info(
                            "KRX로부터 %d개 가격 "
                            "레코드 수신 완료",
                            len(kr_records),
                        )

                        if kr_records:
                            sources_used.append(
                                "krx"
                            )

                        # KRX가 제공한 실제 종목 마스터가 있으면
                        # 현재 수집 대상만 선별하여 반영합니다.
                        if getattr(
                            client,
                            "last_etf_master",
                            None,
                        ):
                            target_ticker_set = set(
                                kr_tickers
                            )

                            selected_master = [
                                item
                                for item
                                in client.last_etf_master
                                if (
                                    str(
                                        item.get(
                                            "ticker",
                                            "",
                                        )
                                    )
                                    .strip()
                                    .zfill(6)
                                    in target_ticker_set
                                )
                            ]

                            if selected_master:
                                master_saved = (
                                    repository
                                    .save_etf_master(
                                        selected_master
                                    )
                                )

                                logger.info(
                                    "가격 수집 대상 ETF "
                                    "마스터 동기화 완료: "
                                    "%d건 반영",
                                    master_saved,
                                )

                        # KRX에서 가격을 받지 못한 국내 종목만
                        # 네이버 금융으로 보완합니다.
                        fetched_tickers = {
                            str(
                                record.get(
                                    "ticker",
                                    "",
                                )
                            )
                            .strip()
                            .zfill(6)
                            for record in kr_records
                            if record.get(
                                "ticker"
                            )
                        }

                        missing_kr = [
                            ticker
                            for ticker in kr_tickers
                            if ticker
                            not in fetched_tickers
                        ]

                        if missing_kr:
                            logger.info(
                                "KRX 누락 국내 종목 "
                                "%d개를 네이버 금융에서 "
                                "추가 수집합니다: %s",
                                len(missing_kr),
                                missing_kr,
                            )

                            from data.naver_client import (
                                NaverFinanceClient,
                            )

                            naver_client = (
                                NaverFinanceClient()
                            )

                            extra_records = (
                                naver_client
                                .fetch_historical_prices(
                                    missing_kr,
                                    days=days,
                                )
                            )

                            if extra_records:
                                sources_used.append(
                                    "naver"
                                )

                            kr_records.extend(
                                extra_records
                            )

                    else:
                        logger.warning(
                            "KRX_API_KEY가 설정되지 않아 "
                            "국내 종목을 네이버 금융에서 "
                            "수집합니다."
                        )

                        kr_source = "naver"

                except Exception as exc:
                    logger.error(
                        "KRX API 수집 실패: %s. "
                        "국내 종목을 네이버 금융에서 "
                        "수집합니다.",
                        exc,
                    )

                    kr_source = "naver"

            # -----------------------------------------------------
            # 7-2. 네이버 금융
            # -----------------------------------------------------
            if kr_source == "naver":
                try:
                    logger.info(
                        "네이버 금융 가격 데이터 "
                        "수집 시작 (종목: %s)",
                        kr_tickers,
                    )

                    from data.naver_client import (
                        NaverFinanceClient,
                    )

                    naver_client = (
                        NaverFinanceClient()
                    )

                    kr_records = (
                        naver_client
                        .fetch_historical_prices(
                            kr_tickers,
                            days=days,
                        )
                    )

                    if kr_records:
                        sources_used.append(
                            "naver"
                        )

                    logger.info(
                        "네이버 금융으로부터 "
                        "%d개 가격 레코드 수신 완료",
                        len(kr_records),
                    )

                except Exception as exc:
                    logger.error(
                        "네이버 금융 시세 수집 실패: %s",
                        exc,
                    )

            records.extend(
                kr_records
            )

        # ---------------------------------------------------------
        # 8. 미국 가격 수집
        # ---------------------------------------------------------
        if us_tickers:
            try:
                logger.info(
                    "Yahoo Finance 미국 가격 데이터 "
                    "수집 시작 (종목: %s)",
                    us_tickers,
                )

                yfinance_client = (
                    YFinanceClient()
                )

                us_records = (
                    yfinance_client
                    .fetch_historical_prices(
                        us_tickers,
                        days=days,
                    )
                )

                if us_records:
                    sources_used.append(
                        "yfinance"
                    )

                records.extend(
                    us_records
                )

                logger.info(
                    "Yahoo Finance로부터 "
                    "%d개 미국 가격 레코드 "
                    "수신 완료",
                    len(us_records),
                )

            except Exception as exc:
                # 미국 가격 수집 실패가 국내 가격까지
                # 폐기하지 않도록 독립적으로 처리합니다.
                logger.error(
                    "Yahoo Finance 미국 시세 "
                    "수집 실패: %s",
                    exc,
                )

    # -------------------------------------------------------------
    # 9. 수집 결과 확인
    # -------------------------------------------------------------
    if not records:
        data_source_used = (
            ",".join(sources_used)
            if sources_used
            else configured_source
        )

        logger.warning(
            "시장 가격 데이터 수집 실패 (%s). "
            "기존 DB 가격 데이터는 유지합니다.",
            data_source_used,
        )

        return {
            "status": "warning",
            "data_source":
                data_source_used,
            "records_count": 0,
            "saved_count": 0,
            "kr_tickers":
                len(kr_tickers),
            "us_tickers":
                len(us_tickers),
            "message": (
                "실제 시세 수집에 실패하여 "
                "기존 DB 데이터를 유지합니다."
            ),
        }

    # -------------------------------------------------------------
    # 10. 가격 레코드 정규화, 검증 및
    #     asset_master 최종 확인
    # -------------------------------------------------------------
    normalized_records: List[
        Dict[str, Any]
    ] = []

    invalid_record_count = 0


    def safe_float(
        value: Any,
        default: float = 0.0,
    ) -> float:
        """
        외부 가격 데이터를 안전한 유한 실수로 변환합니다.

        None, NaN, Infinity, 변환 불가능한 값은
        default 값으로 처리합니다.
        """
        if value is None:
            return default

        try:
            number = float(
                value
            )

        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            return default

        if not math.isfinite(
            number
        ):
            return default

        return number


    def safe_int(
        value: Any,
        default: int = 0,
    ) -> int:
        """
        거래량을 안전한 정수로 변환합니다.
        """
        number = safe_float(
            value,
            float(default),
        )

        try:
            return int(
                number
            )

        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            return default


    def normalize_price_date(
        value: Any,
    ) -> Optional[str]:
        """
        가격 날짜를 YYYYMMDD 형식으로 정규화합니다.

        지원 형식:
        - YYYYMMDD
        - YYYY-MM-DD
        """
        clean_value = (
            str(
                value
                or ""
            )
            .strip()
        )

        if not clean_value:
            return None

        for date_format in (
            "%Y%m%d",
            "%Y-%m-%d",
        ):
            try:
                parsed_date = (
                    datetime.strptime(
                        clean_value,
                        date_format,
                    )
                )

                return (
                    parsed_date.strftime(
                        "%Y%m%d"
                    )
                )

            except ValueError:
                continue

        return None


    for source_record in records:

        if not isinstance(
            source_record,
            dict,
        ):
            invalid_record_count += 1

            logger.warning(
                "가격 레코드 형식이 올바르지 않아 "
                "건너뜁니다: %r",
                source_record,
            )

            continue


        ticker = (
            str(
                source_record.get(
                    "ticker",
                    "",
                )
            )
            .strip()
            .upper()
        )

        if not ticker:
            invalid_record_count += 1

            logger.warning(
                "ticker가 없는 가격 레코드를 "
                "건너뜁니다."
            )

            continue


        info = asset_info.get(
            ticker
        )


        # 공급자가 국내 종목코드를 숫자로 반환한 경우만
        # 6자리 종목코드로 정규화합니다.
        if (
            info is None
            and ticker.isdigit()
        ):
            padded_ticker = (
                ticker.zfill(6)
            )

            if padded_ticker in asset_info:
                ticker = (
                    padded_ticker
                )

                info = (
                    asset_info.get(
                        ticker
                    )
                )


        price_date = (
            normalize_price_date(
                source_record.get(
                    "date"
                )
            )
        )

        if price_date is None:
            invalid_record_count += 1

            logger.warning(
                "가격 날짜가 올바르지 않아 "
                "건너뜁니다: %s / %r",
                ticker,
                source_record.get(
                    "date"
                ),
            )

            continue


        close_price = (
            safe_float(
                source_record.get(
                    "close_price"
                )
            )
        )


        # 종가는 차트와 현재가 계산의 핵심 값이므로
        # 정상적인 양수가 아니면 해당 가격행 전체를
        # 저장하지 않습니다.
        if close_price <= 0:
            invalid_record_count += 1

            logger.warning(
                "비정상 종가 가격 레코드를 "
                "건너뜁니다: %s / %s / %r",
                ticker,
                price_date,
                source_record.get(
                    "close_price"
                ),
            )

            continue


        open_price = (
            safe_float(
                source_record.get(
                    "open_price"
                )
            )
        )

        high_price = (
            safe_float(
                source_record.get(
                    "high_price"
                )
            )
        )

        low_price = (
            safe_float(
                source_record.get(
                    "low_price"
                )
            )
        )


        # 시가가 없거나 비정상이면 종가를 사용합니다.
        if open_price <= 0:
            open_price = (
                close_price
            )


        # 고가가 없거나 비정상이면
        # 시가와 종가 중 큰 값을 사용합니다.
        if high_price <= 0:
            high_price = max(
                open_price,
                close_price,
            )


        # 저가가 없거나 비정상이면
        # 시가와 종가 중 작은 값을 사용합니다.
        if low_price <= 0:
            low_price = min(
                open_price,
                close_price,
            )


        # 공급자가 비정상적인 OHLC 관계를 보내는 경우
        # 차트 왜곡을 막기 위해 고가와 저가의 범위를
        # 시가/종가까지 포함하도록 보정합니다.
        high_price = max(
            high_price,
            open_price,
            close_price,
        )

        low_price = min(
            low_price,
            open_price,
            close_price,
        )


        price_values = (
            open_price,
            high_price,
            low_price,
            close_price,
        )


        if not all(
            math.isfinite(
                value
            )
            and value > 0
            for value in price_values
        ):
            invalid_record_count += 1

            logger.warning(
                "유효하지 않은 OHLC 가격을 "
                "건너뜁니다: %s / %s",
                ticker,
                price_date,
            )

            continue


        volume = (
            safe_int(
                source_record.get(
                    "volume",
                    0,
                )
            )
        )

        if volume < 0:
            volume = 0


        nav = (
            safe_float(
                source_record.get(
                    "nav",
                    close_price,
                )
            )
        )

        if nav <= 0:
            nav = (
                close_price
            )


        trading_value = (
            safe_float(
                source_record.get(
                    "trading_value",
                    0,
                )
            )
        )

        if trading_value < 0:
            trading_value = 0.0


        if not repository.get_etf_master(
            ticker
        ):
            if info:
                repository.save_etf_master(
                    [info]
                )

            else:
                # 현재 수집 대상에 없는 예상 외 ticker는
                # 임의로 국가나 시장을 추측하지 않고
                # 저장하지 않습니다.
                logger.warning(
                    "asset_master 정보가 없는 "
                    "예상 외 ticker를 건너뜁니다: %s",
                    ticker,
                )

                invalid_record_count += 1

                continue


        # 원본 공급자 딕셔너리를 직접 수정하지 않고
        # DB 저장용 레코드를 별도로 생성합니다.
        normalized_record = dict(
            source_record
        )

        normalized_record.update(
            {
                "date":
                    price_date,

                "ticker":
                    ticker,

                "open_price":
                    open_price,

                "high_price":
                    high_price,

                "low_price":
                    low_price,

                "close_price":
                    close_price,

                "nav":
                    nav,

                "volume":
                    volume,

                "trading_value":
                    trading_value,
            }
        )


        normalized_records.append(
            normalized_record
        )


    if invalid_record_count > 0:
        logger.warning(
            "가격 데이터 최종 검증에서 "
            "%d건을 제외했습니다.",
            invalid_record_count,
        )
        

    if not normalized_records:
        logger.warning(
            "저장 가능한 가격 레코드가 없습니다. "
            "기존 DB 가격 데이터는 유지합니다."
        )

        return {
            "status": "warning",
            "data_source": (
                ",".join(
                    dict.fromkeys(
                        sources_used
                    )
                )
                if sources_used
                else configured_source
            ),
            "records_count": 0,
            "saved_count": 0,
            "kr_tickers":
                len(kr_tickers),
            "us_tickers":
                len(us_tickers),
            "message": (
                "정규화 후 저장 가능한 "
                "가격 데이터가 없습니다."
            ),
        }

    # -------------------------------------------------------------
    # 11. PostgreSQL/Supabase 가격 저장
    # -------------------------------------------------------------
    saved_count = (
        repository.upsert_prices(
            normalized_records
        )
    )

    unique_sources = list(
        dict.fromkeys(
            sources_used
        )
    )

    data_source_used = (
        ",".join(unique_sources)
        if unique_sources
        else configured_source
    )

    logger.info(
        "DB 가격 저장 완료: %d건 반영 "
        "(KR %d종목, US %d종목, source=%s)",
        saved_count,
        len(kr_tickers),
        len(us_tickers),
        data_source_used,
    )

    return {
        "status": "success",
        "data_source":
            data_source_used,
        "records_count":
            len(normalized_records),
        "saved_count":
            saved_count,
        "kr_tickers":
            len(kr_tickers),
        "us_tickers":
            len(us_tickers),
    }


def main():
    """CLI 및 GitHub Actions 실행 진입점."""
    setup_logging()

    logger.info(
        "CLI 기반 시장 데이터 업데이트 "
        "작업을 시작합니다."
    )

    report_user_id = (
        os.getenv(
            "REPORT_USER_ID",
            ""
        )
        .strip()
    )

    if not report_user_id:
        logger.error(
            "REPORT_USER_ID 환경변수가 "
            "설정되지 않았습니다."
        )

        sys.exit(1)

    logger.info(
        "사용자 포트폴리오를 포함하여 "
        "시장 가격을 업데이트합니다."
    )

    try:
        result = (
            update_market_prices(
                user_id=report_user_id
            )
        )

        print(
            f"업데이트 완료: {result}"
        )

        logger.info(
            "작업 정상 종료: %s",
            result,
        )

    except Exception as exc:
        logger.exception(
            "데이터 업데이트 중 "
            "치명적 오류 발생: %s",
            exc,
        )

        sys.exit(1)

if __name__ == "__main__":
    main()
