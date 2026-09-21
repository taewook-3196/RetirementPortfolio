"""
data/price_updater.py
ETF 시장 가격 데이터를 수집하고 SQLite DB에 저장/갱신하는 모듈.
GUI의 [시장 데이터 업데이트] 버튼 및 Windows 작업 스케줄러 CLI 실행을 모두 지원합니다.
실행 예: python -m data.price_updater
"""

from __future__ import annotations
import sys
import logging
from typing import Dict, Any, List, Optional
from core.paths import ensure_directories
from core.config import load_config, AppConfig
from core.logging_config import setup_logging
from database.connection import init_db
from database.repository import Repository
from data.krx_client import KRXClient
from data.mock_provider import MockDataProvider

logger = logging.getLogger("RetirementPortfolio.PriceUpdater")


def update_market_prices(
    config: Optional[AppConfig] = None,
    repo: Optional[Repository] = None,
    days: int = 90,
    scenario: str = "normal",
) -> Dict[str, Any]:
    """
    설정에 지정된 ETF들의 최신 가격 데이터를 수집하여 DB에 저장합니다.
    - config.data_source가 'krx'이면 KRX Open API 호출
    - 'mock'이거나 KRX 호출 실패 시 MockDataProvider 활용
    """
    ensure_directories()
    cfg = config or load_config()
    repository = repo or Repository()
    init_db(repository.db_path)

    seen_tickers = set()
    target_tickers: List[str] = []
    etf_info_list: List[Dict[str, str]] = []

    for e in cfg.etfs:
        t_code = str(e.ticker).strip().zfill(6)
        if t_code not in seen_tickers:
            seen_tickers.add(t_code)
            target_tickers.append(t_code)
            etf_info_list.append({"ticker": t_code, "name": e.name})

    for w in getattr(cfg, "watchlist", []):
        t_code = str(w.ticker).strip().zfill(6)
        if t_code not in seen_tickers:
            seen_tickers.add(t_code)
            target_tickers.append(t_code)
            etf_info_list.append({"ticker": t_code, "name": w.name})

    # 모든 계좌의 목표 종목 및 실제 거래내역 종목도 수집 대상에 포함
    all_targets = repository.get_account_targets(account_id=None)
    for t in all_targets:
        t_code = str(t.ticker).strip().zfill(6)
        if t_code not in seen_tickers:
            seen_tickers.add(t_code)
            target_tickers.append(t_code)
            etf_info_list.append({"ticker": t_code, "name": t.name})

    for tx in repository.get_transactions():
        t_code = str(tx.ticker).strip().zfill(6)
        if t_code not in seen_tickers:
            seen_tickers.add(t_code)
            target_tickers.append(t_code)
            master = repository.get_etf_master(t_code)
            etf_info_list.append({"ticker": t_code, "name": master.name if master else t_code})

    # 모닝 리포트 시장 지표용 대표 ETF (KODEX 200) 보장
    if "069500" not in seen_tickers:
        seen_tickers.add("069500")
        target_tickers.append("069500")
        etf_info_list.append({"ticker": "069500", "name": "KODEX 200"})

    data_source_used = cfg.data_source.lower()
    records: List[Dict[str, Any]] = []

    # 1. KRX API 시도
    if data_source_used == "krx":
        try:
            client = KRXClient()
            if client.is_configured():
                logger.info("KRX 공식 Open API를 통해 가격 데이터 수집 시작 (종목: %s)", target_tickers)
                records = client.fetch_historical_prices(target_tickers, days=days)
                logger.info("KRX로부터 %d개 레코드 수신 완료", len(records))
                if getattr(client, "last_etf_master", None):
                    master_saved = repository.save_etf_master(client.last_etf_master)
                    logger.info("전체 ETF 마스터 동기화 완료: %d건 반영됨", master_saved)
                
                # 누락된 종목이 있다면 네이버 금융으로 보완
                fetched_tickers = {r["ticker"] for r in records}
                missing = [t for t in target_tickers if t not in fetched_tickers]
                if missing:
                    logger.info("KRX에서 누락된 %d개 종목을 네이버 금융에서 추가 수집합니다: %s", len(missing), missing)
                    from data.naver_client import NaverFinanceClient
                    n_client = NaverFinanceClient()
                    extra_records = n_client.fetch_historical_prices(missing, days=days)
                    records.extend(extra_records)
            else:
                logger.warning("KRX_API_KEY 미설정 -> 네이버 금융 실시간 시세로 전환합니다.")
                data_source_used = "naver"
        except Exception as e:
            logger.error("KRX API 수집 실패: %s -> 네이버 금융 실시간 시세로 대체합니다.", e)
            data_source_used = "naver (fallback)"

    # 2. 네이버 금융 (또는 real 모드, 또는 KRX 실패 시)
    if data_source_used.startswith("naver") or data_source_used == "real":
        try:
            logger.info("네이버 금융 실시간 시세를 통해 가격 데이터 수집 시작 (종목: %s)", target_tickers)
            from data.naver_client import NaverFinanceClient
            n_client = NaverFinanceClient()
            records = n_client.fetch_historical_prices(target_tickers, days=days)
            data_source_used = "naver"
            logger.info("네이버 금융으로부터 %d개 레코드 수신 완료", len(records))
        except Exception as e:
            logger.error("네이버 금융 시세 수집 실패: %s -> Mock 데이터로 대체합니다.", e)
            data_source_used = "mock (fallback)"

    # 3. Mock 시뮬레이션 (설정이 mock이거나 외부 네트워크 모두 실패 시)
    if not records or data_source_used.startswith("mock"):
        logger.info("MockDataProvider를 통해 데이터 생성 (시나리오: %s)", scenario)
        mock = MockDataProvider(scenario=scenario)
        records = mock.get_historical_prices(etf_info_list, days=days)
        if not data_source_used.startswith("mock"):
            data_source_used = "mock (fallback)"

    saved_count = repository.upsert_prices(records)
    logger.info("DB 가격 저장 완료: %d건 반영됨", saved_count)

    return {
        "status": "success",
        "data_source": data_source_used,
        "records_count": len(records),
        "saved_count": saved_count,
    }


def main():
    """Windows 작업 스케줄러 및 CLI 실행 진입점"""
    setup_logging()
    logger.info("CLI 기반 시장 데이터 업데이트 작업을 시작합니다.")
    try:
        result = update_market_prices()
        print(f"업데이트 완료: {result}")
        logger.info("작업 정상 종료: %s", result)
    except Exception as e:
        logger.exception("데이터 업데이트 중 치명적 오류 발생: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
