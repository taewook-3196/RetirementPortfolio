"""
database/connection.py
Supabase PostgreSQL 데이터베이스 연결 관리.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

_engine: Engine | None = None
_SessionFactory: sessionmaker | None = None


def get_engine() -> Engine:
    """환경변수 DATABASE_URL을 사용하여 PostgreSQL Engine을 반환합니다."""
    global _engine, _SessionFactory

    if _engine is None:
        database_url = os.getenv("DATABASE_URL", "").strip()

        if not database_url:
            raise RuntimeError(
                "DATABASE_URL 환경변수가 설정되지 않았습니다."
            )

        _engine = create_engine(
            database_url,
            echo=False,
            pool_pre_ping=True,
        )

        _SessionFactory = sessionmaker(
            bind=_engine,
            expire_on_commit=False,
        )

    return _engine


def init_db() -> None:
    """
    데이터베이스 연결을 확인합니다.

    Supabase의 테이블과 RLS 정책은 Supabase SQL Editor에서 관리하므로
    애플리케이션에서 자동으로 테이블을 생성하거나 변경하지 않습니다.
    """
    engine = get_engine()

    with engine.connect() as connection:
        connection.exec_driver_sql("SELECT 1")


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """SQLAlchemy 세션을 안전하게 제공합니다."""
    global _SessionFactory

    get_engine()

    if _SessionFactory is None:
        raise RuntimeError("데이터베이스 세션을 초기화할 수 없습니다.")

    session: Session = _SessionFactory()

    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
