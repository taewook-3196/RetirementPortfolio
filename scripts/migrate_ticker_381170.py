"""
scripts/migrate_ticker_381170.py
453330 -> 381170 (TIGER 미국테크TOP10 INDXX) 데이터베이스 마이그레이션 스크립트.
- transactions 테이블의 ticker '453330' -> '381170' 갱신
- recommendation_logs 테이블의 ticker '453330' -> '381170' 갱신
- 381170 종목의 최근 90일 시세 KRX Open API로부터 수신하여 prices 테이블에 upsert
"""

import sys
import os
import sqlite3
import logging
from core.paths import get_database_path, ensure_directories
from core.config import load_config
from core.logging_config import setup_logging
from database.repository import Repository
from data.price_updater import update_market_prices

setup_logging()
logger = logging.getLogger("MigrateTicker")

def run_migration():
    db_path = str(get_database_path())
    logger.info("데이터베이스 연결: %s", db_path)

    con = sqlite3.connect(db_path)
    cur = con.cursor()

    # 1. transactions 갱신
    cur.execute("SELECT COUNT(*) FROM transactions WHERE ticker = '453330'")
    tx_count = cur.fetchone()[0]
    if tx_count > 0:
        cur.execute("UPDATE transactions SET ticker = '381170' WHERE ticker = '453330'")
        con.commit()
        logger.info("transactions 테이블: %d건의 453330 거래를 381170으로 변경 완료", tx_count)
    else:
        logger.info("transactions 테이블: 453330 거래가 없습니다.")

    # 2. recommendation_logs 갱신
    try:
        cur.execute("SELECT COUNT(*) FROM recommendation_logs WHERE ticker = '453330'")
        log_count = cur.fetchone()[0]
        if log_count > 0:
            cur.execute("UPDATE recommendation_logs SET ticker = '381170' WHERE ticker = '453330'")
            con.commit()
            logger.info("recommendation_logs 테이블: %d건의 453330 기록을 381170으로 변경 완료", log_count)
    except Exception as e:
        logger.warning("recommendation_logs 처리 중 예외 (무시 가능): %s", e)

    # 3. etf_master 확인 및 보정
    cur.execute("INSERT OR REPLACE INTO etf_master (ticker, name) VALUES ('381170', 'TIGER 미국테크TOP10 INDXX')")
    con.commit()
    con.close()

    # 4. 최신 시장 가격 업데이트 (381170 포함)
    logger.info("시장 데이터 수집 시작 (config.yaml 기준 381170 포함)")
    cfg = load_config()
    res = update_market_prices(config=cfg, days=90)
    logger.info("시장 데이터 업데이트 결과: %s", res)

if __name__ == "__main__":
    run_migration()
