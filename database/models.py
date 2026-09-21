"""
database/models.py
SQLAlchemy ORM 데이터베이스 모델 정의.
- Price: 일별 ETF 가격 히스토리 (시가, 고가, 저가, 종가, NAV, 거래량, 거래대금)
- Transaction: 매매 및 거래 내역 (BUY, SELL, DIVIDEND)
- Dividend: 분배금 수령 내역
- RecommendationLog: 월간 매수 추천 기록
"""

from __future__ import annotations
from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    Text,
    UniqueConstraint,
    Index,
    ForeignKey,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Account(Base):
    """관리 대상 계좌 모델 (신한 IRP, 미래에셋 연금저축 등)"""
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_name = Column(String(100), nullable=False, unique=True, index=True)
    account_number = Column(String(50), nullable=True, default="")
    broker = Column(String(50), nullable=True, default="")
    initial_capital = Column(Float, nullable=False, default=100000000.0)
    base_monthly = Column(Float, nullable=False, default=10000000.0)
    max_additional_monthly = Column(Float, nullable=False, default=3000000.0)
    buy_cycle_type = Column(String(20), nullable=False, default="monthly")  # none, daily, weekly, biweekly, monthly, bimonthly, quarterly
    buy_cycle_detail = Column(String(50), nullable=False, default="25")     # 요일(MON~FRI) 또는 일자(1~28, last)
    is_default = Column(Integer, nullable=False, default=0)
    memo = Column(String(255), nullable=True, default="")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self) -> str:
        return f"<Account(id={self.id}, name='{self.account_name}', broker='{self.broker}', cycle='{self.buy_cycle_type}:{self.buy_cycle_detail}')>"


class AccountTarget(Base):
    """계좌별 ETF 목표 비중 모델"""
    __tablename__ = "account_targets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    ticker = Column(String(20), nullable=False)
    name = Column(String(100), nullable=True)
    target_weight = Column(Float, nullable=False, default=0.0)
    dividend_yield = Column(Float, nullable=False, default=0.0)

    __table_args__ = (
        UniqueConstraint("account_id", "ticker", name="uq_account_ticker_target"),
    )

    def __repr__(self) -> str:
        return f"<AccountTarget(account_id={self.account_id}, ticker='{self.ticker}', weight={self.target_weight})>"


class Price(Base):
    """ETF 일별 가격 데이터 모델"""
    __tablename__ = "prices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD or YYYYMMDD
    ticker = Column(String(20), nullable=False, index=True)
    name = Column(String(100), nullable=True)
    open_price = Column(Float, nullable=False, default=0.0)
    high_price = Column(Float, nullable=False, default=0.0)
    low_price = Column(Float, nullable=False, default=0.0)
    close_price = Column(Float, nullable=False, default=0.0)
    nav = Column(Float, nullable=True, default=0.0)
    volume = Column(Integer, nullable=False, default=0)
    trading_value = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        UniqueConstraint("date", "ticker", name="uq_prices_date_ticker"),
        Index("idx_prices_ticker_date", "ticker", "date"),
    )

    def __repr__(self) -> str:
        return f"<Price(date='{self.date}', ticker='{self.ticker}', close={self.close_price})>"


class Transaction(Base):
    """사용자 거래 내역 모델 (매수, 매도, 분배금 등)"""
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True, index=True)
    transaction_date = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    ticker = Column(String(20), nullable=False, index=True)
    transaction_type = Column(String(10), nullable=False)  # BUY, SELL, DIVIDEND
    quantity = Column(Integer, nullable=False, default=0)
    price = Column(Float, nullable=False, default=0.0)
    fee = Column(Float, nullable=False, default=0.0)
    tax = Column(Float, nullable=False, default=0.0)
    memo = Column(String(255), nullable=True, default="")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self) -> str:
        return (
            f"<Transaction(id={self.id}, account_id={self.account_id}, date='{self.transaction_date}', "
            f"ticker='{self.ticker}', type='{self.transaction_type}', qty={self.quantity}, price={self.price})>"
        )


class Dividend(Base):
    """분배금 수령 내역 모델"""
    __tablename__ = "dividends"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True, index=True)
    dividend_date = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    ticker = Column(String(20), nullable=False, index=True)
    gross_amount = Column(Float, nullable=False, default=0.0)
    tax = Column(Float, nullable=False, default=0.0)
    net_amount = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, default=datetime.now)

    def __repr__(self) -> str:
        return f"<Dividend(date='{self.dividend_date}', ticker='{self.ticker}', net={self.net_amount})>"


class RecommendationLog(Base):
    """월간 매수 추천 히스토리 모델"""
    __tablename__ = "recommendation_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    recommendation_date = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    ticker = Column(String(20), nullable=False)
    name = Column(String(100), nullable=True)
    target_weight = Column(Float, nullable=False)
    current_weight = Column(Float, nullable=False)
    weight_gap = Column(Float, nullable=False)
    recent_high = Column(Float, nullable=False)
    current_price = Column(Float, nullable=False)
    drawdown = Column(Float, nullable=False)
    drawdown_score = Column(Integer, nullable=False, default=0)
    priority_score = Column(Float, nullable=False, default=0.0)
    recommended_buy = Column(Integer, nullable=False, default=0)
    expected_weight_after = Column(Float, nullable=False, default=0.0)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    def __repr__(self) -> str:
        return (
            f"<RecommendationLog(date='{self.recommendation_date}', ticker='{self.ticker}', "
            f"buy={self.recommended_buy})>"
        )


class ETFMaster(Base):
    """국내 상장 ETF 마스터 목록 (종목코드, 종목명)"""
    __tablename__ = "etf_master"

    ticker = Column(String(20), primary_key=True)
    name = Column(String(100), nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self) -> str:
        return f"<ETFMaster(ticker='{self.ticker}', name='{self.name}')>"

