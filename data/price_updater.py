"""
data/price_updater.py

ETF 시장 가격 데이터를 수집하고 PostgreSQL/Supabase DB에 저장/갱신하는 모듈.

- KRX 공식 Open API 우선 사용
- KRX 누락 또는 실패 시 네이버 금융 데이터 사용
- 가격 저장 전에 asset_master 종목 정보를 보장
- 사용자별 계좌 목표 종목 및 거래 종목을 수집 대상에 포함
- CLI 및 GitHub Actions 실행 지원
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Dict, List, Optional

from core.config import AppConfig, load_config
from core.logging_config import setup_logging
from core.paths import ensure_directories
from database.repository import Repository
from data.krx_client import KRXClient


logger = logging.getLogger("RetirementPortfolio.PriceUpdater")


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

    user_id가 있으면 해당 사용자의 계좌 목표 종목과 실제 거래 종목도
    가격 수집 대상에 포함합니다.
    """
    ensure_directories()

    cfg = config or load_config()
    repository = repo or Repository(user_id=user_id)

    seen_tickers = set()
    target_tickers: List[str] = []
    asset_info: Dict[str, Dict[str, str]] = {}

    def add_target(
        ticker: str,
        name: str,
        market: str = "KR",
        exchange: str = "KRX",
        asset_type: str = "ETF",
        currency: str = "KRW",
    ) -> None:
        """
        가격 수집 대상 종목을 중복 없이 추가하고,
        asset_master 저장에 필요한 정보도 함께 준비합니다.
        """
        clean_ticker = str(ticker).strip()

        if not clean_ticker:
            return

        # 현재 국내 종목코드는 6자리 형식으로 정규화
        if market.upper() == "KR" and clean_ticker.isdigit():
            clean_ticker = clean_ticker.zfill(6)

        clean_name = str(name or clean_ticker).strip()

        if clean_ticker not in seen_tickers:
            seen_tickers.add(clean_ticker)
            target_tickers.append(clean_ticker)

        asset_info[clean_ticker] = {
            "ticker": clean_ticker,
            "name": clean_name,
            "market": str(market or "KR").upper(),
            "exchange": str(exchange or "KRX").upper(),
            "asset_type": str(asset_type or "ETF").upper(),
            "currency": str(currency or "KRW").upper(),
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
    for watch in getattr(cfg, "watchlist", []):
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
        for target in repository.get_account_targets(account_id=None):
            master = repository.get_etf_master(target.ticker)

            if master:
                add_target(
                    ticker=master.ticker,
                    name=master.name,
                    market=master.market,
                    exchange=master.exchange or "KRX",
                    asset_type=master.asset_type,
                    currency=master.currency,
                )
            else:
                add_target(
                    ticker=target.ticker,
                    name=target.name,
                )

        for tx in repository.get_transactions():
            master = repository.get_etf_master(tx.ticker)

            if master:
                add_target(
                    ticker=master.ticker,
                    name=master.name,
                    market=master.market,
                    exchange=master.exchange or "KRX",
                    asset_type=master.asset_type,
                    currency=master.currency,
                )
            else:
                add_target(
                    ticker=tx.ticker,
                    name=tx.ticker,
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

    # 가격을 저장하기 전에 기본 자산 마스터를 먼저 보장한다.
    repository.save_etf_master(list(asset_info.values()))

    data_source_used = str(cfg.data_source).lower()
    records: List[Dict[str, Any]] = []

    # -------------------------------------------------------------
    # 5. Mock 데이터
    # -------------------------------------------------------------
    if data_source_used == "mock":
        from data.mock_provider import MockDataProvider

        mock_provider = MockDataProvider(scenario=scenario)

        records = mock_provider.get_historical_prices(
            list(asset_info.values()),
            days=days,
        )

        logger.info(
            "MockDataProvider 데이터 생성 완료 "
            "(시나리오: %s, 종목: %s)",
            scenario,
            target_tickers,
        )

    # -------------------------------------------------------------
    # 6. KRX 공식 Open API
    # -------------------------------------------------------------
    elif data_source_used == "krx":
        try:
            client = KRXClient()

            if client.is_configured():
                logger.info(
                    "KRX 공식 Open API 가격 데이터 수집 시작 "
                    "(종목: %s)",
                    target_tickers,
                )

                records = client.fetch_historical_prices(
                    target_tickers,
                    days=days,
                )

                logger.info(
                    "KRX로부터 %d개 가격 레코드 수신 완료",
                    len(records),
                )

                # KRX가 제공한 실제 종목 마스터 정보가 있으면
                # 기존 기본 정보를 더 정확한 정보로 갱신
                if getattr(client, "last_etf_master", None):
                    master_saved = repository.save_etf_master(
                        client.last_etf_master
                    )

                    logger.info(
                        "KRX ETF 마스터 동기화 완료: %d건 반영",
                        master_saved,
                    )

                # KRX에서 가격을 받지 못한 종목은 네이버 금융으로 보완
                fetched_tickers = {
                    str(record.get("ticker", "")).strip()
                    for record in records
                    if record.get("ticker")
                }

                missing = [
                    ticker
                    for ticker in target_tickers
                    if ticker not in fetched_tickers
                ]

                if missing:
                    logger.info(
                        "KRX 누락 종목 %d개를 네이버 금융에서 "
                        "추가 수집합니다: %s",
                        len(missing),
                        missing,
                    )

                    from data.naver_client import NaverFinanceClient

                    naver_client = NaverFinanceClient()

                    extra_records = (
                        naver_client.fetch_historical_prices(
                            missing,
                            days=days,
                        )
                    )

                    records.extend(extra_records)

            else:
                logger.warning(
                    "KRX_API_KEY가 설정되지 않아 "
                    "네이버 금융으로 전환합니다."
                )

                data_source_used = "naver"

        except Exception as exc:
            logger.error(
                "KRX API 수집 실패: %s. "
                "네이버 금융으로 전환합니다.",
                exc,
            )

            data_source_used = "naver-fallback"

    # -------------------------------------------------------------
    # 7. 네이버 금융
    # -------------------------------------------------------------
    if (
        data_source_used.startswith("naver")
        or data_source_used == "real"
    ):
        try:
            logger.info(
                "네이버 금융 가격 데이터 수집 시작 "
                "(종목: %s)",
                target_tickers,
            )

            from data.naver_client import NaverFinanceClient

            naver_client = NaverFinanceClient()

            records = naver_client.fetch_historical_prices(
                target_tickers,
                days=days,
            )

            data_source_used = "naver"

            logger.info(
                "네이버 금융으로부터 %d개 가격 레코드 수신 완료",
                len(records),
            )

        except Exception as exc:
            logger.error(
                "네이버 금융 시세 수집 실패: %s",
                exc,
            )

    # -------------------------------------------------------------
    # 8. 수집 결과 확인
    # -------------------------------------------------------------
    if not records:
        logger.warning(
            "시장 가격 데이터 수집 실패 (%s). "
            "기존 DB 가격 데이터는 유지합니다.",
            data_source_used,
        )

        return {
            "status": "warning",
            "data_source": data_source_used,
            "records_count": 0,
            "saved_count": 0,
            "message": (
                "실제 시세 수집에 실패하여 "
                "기존 DB 데이터를 유지합니다."
            ),
        }

    # 가격 저장 전에 records에 포함된 모든 ticker가
    # asset_master에 존재하는지 마지막으로 확인
    for record in records:
        ticker = str(record.get("ticker", "")).strip()

        if not ticker:
            continue

        if ticker.isdigit():
            ticker = ticker.zfill(6)

        record["ticker"] = ticker

        if not repository.get_etf_master(ticker):
            info = asset_info.get(ticker)

            if info:
                repository.save_etf_master([info])
            else:
                # 공급자가 예상하지 못한 종목을 반환한 경우
                # FK 오류를 피하기 위해 최소 자산 정보 등록
                repository.save_etf_master(
                    [
                        {
                            "ticker": ticker,
                            "name": ticker,
                            "market": "KR",
                            "exchange": "KRX",
                            "asset_type": "ETF",
                            "currency": "KRW",
                        }
                    ]
                )

    # -------------------------------------------------------------
    # 9. PostgreSQL/Supabase 가격 저장
    # -------------------------------------------------------------
    saved_count = repository.upsert_prices(records)

    logger.info(
        "DB 가격 저장 완료: %d건 반영",
        saved_count,
    )

    return {
        "status": "success",
        "data_source": data_source_used,
        "records_count": len(records),
        "saved_count": saved_count,
    }


def main():
    """CLI 및 GitHub Actions 실행 진입점."""
    setup_logging()

    logger.info(
        "CLI 기반 시장 데이터 업데이트 작업을 시작합니다."
    )

    try:
        result = update_market_prices()

        print(f"업데이트 완료: {result}")

        logger.info(
            "작업 정상 종료: %s",
            result,
        )

    except Exception as exc:
        logger.exception(
            "데이터 업데이트 중 치명적 오류 발생: %s",
            exc,
        )

        sys.exit(1)


if __name__ == "__main__":
    main()
