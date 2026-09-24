"""
data/asset_master_updater.py

KRX 전체 국내 종목 마스터를 갱신하는 모듈.

- ETF
- KOSPI
- KOSDAQ

가격 데이터와 분리하여 저빈도로 실행합니다.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta

from core.logging_config import setup_logging
from database.repository import Repository
from data.krx_client import KRXClient


logger = logging.getLogger(
    "RetirementPortfolio.AssetMasterUpdater"
)


def update_asset_master() -> dict:
    """
    최근 영업일의 KRX 전체 종목 마스터를
    Supabase asset_master에 저장합니다.
    """
    client = KRXClient()

    if not client.is_configured():
        raise RuntimeError(
            "KRX_API_KEY가 설정되지 않았습니다."
        )

    repository = Repository()

    # 오늘부터 과거 방향으로 탐색하여
    # 실제 KRX 데이터가 존재하는 최근 영업일을 찾는다.
    current_date = datetime.now()

    for offset in range(10):
        target_date = (
            current_date
            - timedelta(days=offset)
        )

        if target_date.weekday() >= 5:
            continue

        date_str = target_date.strftime(
            "%Y%m%d"
        )

        logger.info(
            "KRX 전체 종목 마스터 조회: %s",
            date_str,
        )

        master = client.fetch_full_asset_master(
            date_str
        )

        if not master:
            continue

        saved_count = (
            repository.save_etf_master(
                master
            )
        )

        logger.info(
            "KRX 전체 종목 마스터 갱신 완료 "
            "(기준일: %s, 수집: %d, 저장: %d)",
            date_str,
            len(master),
            saved_count,
        )

        return {
            "status": "success",
            "date": date_str,
            "records_count": len(master),
            "saved_count": saved_count,
        }

    raise RuntimeError(
        "최근 10일 내 KRX 종목 마스터를 "
        "가져올 수 없습니다."
    )


def main() -> None:
    setup_logging()

    try:
        result = update_asset_master()

        print(
            f"Asset master update result: "
            f"{result}"
        )

    except Exception as exc:
        logger.exception(
            "전체 종목 마스터 갱신 실패: %s",
            exc,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
