"""
database/connection.py
SQLite 데이터베이스 연결 관리 및 SQLAlchemy 세션 제공자.
- WAL(Write-Ahead Logging) 모드 활성화로 동시성 및 안정성 강화
- 외래키 제약조건 활성화
- 자동 테이블 생성(init_db)
"""

from __future__ import annotations
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from core.paths import get_database_path
from database.models import Base

_engine: Engine | None = None
_SessionFactory: sessionmaker | None = None


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """SQLite 성능 및 무결성 강화를 위한 PRAGMA 설정"""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


def get_engine(db_path: Path | str | None = None) -> Engine:
    """SQLAlchemy Engine 싱글톤 인스턴스를 반환합니다."""
    global _engine, _SessionFactory
    if _engine is None or db_path is not None:
        target_path = Path(db_path) if db_path else get_database_path()
        # SQLite 연결 문자열 (Windows 한글/공백 경로 지원)
        db_uri = f"sqlite:///{target_path.as_posix()}"
        _engine = create_engine(
            db_uri,
            echo=False,
            connect_args={"check_same_thread": False},
        )
        _SessionFactory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def init_db(db_path: Path | str | None = None) -> None:
    """데이터베이스 파일 및 정의된 모든 테이블을 자동 생성하고 마이그레이션을 수행합니다."""
    engine = get_engine(db_path)
    Base.metadata.create_all(bind=engine)

    # SQLite 컬럼 추가 마이그레이션 (transactions, dividends)
    with engine.connect() as conn:
        # transactions 테이블 확인
        cursor = conn.connection.cursor()
        cursor.execute("PRAGMA table_info(transactions)")
        tx_cols = [row[1] for row in cursor.fetchall()]
        if "account_id" not in tx_cols:
            cursor.execute("ALTER TABLE transactions ADD COLUMN account_id INTEGER")
            conn.connection.commit()

        # dividends 테이블 확인
        cursor.execute("PRAGMA table_info(dividends)")
        div_cols = [row[1] for row in cursor.fetchall()]
        if "account_id" not in div_cols:
            cursor.execute("ALTER TABLE dividends ADD COLUMN account_id INTEGER")
        # accounts 테이블 확인 (buy_cycle_type, buy_cycle_detail)
        cursor.execute("PRAGMA table_info(accounts)")
        acc_cols = [row[1] for row in cursor.fetchall()]
        if "buy_cycle_type" not in acc_cols:
            cursor.execute("ALTER TABLE accounts ADD COLUMN buy_cycle_type VARCHAR(20) DEFAULT 'monthly'")
            conn.connection.commit()
        if "buy_cycle_detail" not in acc_cols:
            cursor.execute("ALTER TABLE accounts ADD COLUMN buy_cycle_detail VARCHAR(50) DEFAULT '25'")
            conn.connection.commit()
        cursor.close()

    # 기본 계좌 확인 및 고아 거래 연결
    from database.models import Account, Transaction, Dividend
    with get_db_session(db_path) as session:
        acc_count = session.query(Account).count()
        default_acc = None
        if acc_count == 0:
            default_acc = Account(
                account_name="기본 계좌 (퇴직연금)",
                account_number="001-000-0000",
                broker="기본 증권",
                initial_capital=100000000.0,
                base_monthly=10000000.0,
                max_additional_monthly=3000000.0,
                is_default=1,
                memo="시스템 기본 계좌",
            )
            session.add(default_acc)
            session.flush()
        else:
            default_acc = session.query(Account).filter(Account.is_default == 1).first()
            if not default_acc:
                default_acc = session.query(Account).first()

        if default_acc:
            session.query(Transaction).filter(Transaction.account_id.is_(None)).update(
                {Transaction.account_id: default_acc.id}, synchronize_session=False
            )
            session.query(Dividend).filter(Dividend.account_id.is_(None)).update(
                {Dividend.account_id: default_acc.id}, synchronize_session=False
            )

            # 기본 계좌 목표 비중 시딩
            from database.models import AccountTarget
            t_count = session.query(AccountTarget).filter(AccountTarget.account_id == default_acc.id).count()
            if t_count == 0:
                from core.config import load_config
                cfg = load_config()
                for etf in cfg.etfs:
                    session.add(
                        AccountTarget(
                            account_id=default_acc.id,
                            ticker=etf.ticker,
                            name=etf.name,
                            target_weight=etf.target_weight,
                            dividend_yield=etf.dividend_yield,
                        )
                    )




@contextmanager
def get_db_session(db_path: Path | str | None = None) -> Generator[Session, None, None]:
    """트랜잭션을 안전하게 처리하는 세션 컨텍스트 매니저를 제공합니다."""
    global _SessionFactory
    get_engine(db_path)
    session: Session = _SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
