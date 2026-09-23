"""
database/models.py
Supabase PostgreSQL용 SQLAlchemy ORM 모델 정의.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import declarative_base


Base = declarative_base()


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(UUID(as_uuid=True), primary_key=True)
    display_name = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now)


class Account(Base):
    __tablename__ = "accounts"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(
        UUID(as_uuid=True),        
        nullable=False,
        index=True,
    )
    account_name = Column(Text, nullable=False)
    account_number = Column(Text, nullable=True)
    broker = Column(Text, nullable=True)
    initial_capital = Column(Numeric, nullable=False, default=0)
    base_monthly = Column(Numeric, nullable=False, default=0)
    max_additional_monthly = Column(Numeric, nullable=False, default=0)
    buy_cycle_type = Column(Text, nullable=False, default="monthly")
    buy_cycle_detail = Column(Text, nullable=False, default="25")
    is_default = Column(Boolean, nullable=False, default=False)
    memo = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now)


class AssetMaster(Base):
    __tablename__ = "asset_master"

    ticker = Column(Text, primary_key=True)
    name = Column(Text, nullable=False)
    market = Column(Text, nullable=False)
    exchange = Column(Text, nullable=True)
    asset_type = Column(Text, nullable=False, default="STOCK")
    currency = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now)


class AccountTarget(Base):
    __tablename__ = "account_targets"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(
        BigInteger,
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ticker = Column(
        Text,
        ForeignKey("asset_master.ticker"),
        nullable=False,
    )
    target_weight = Column(Numeric, nullable=False, default=0)
    dividend_yield = Column(Numeric, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now)

    __table_args__ = (
        UniqueConstraint("account_id", "ticker"),
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(
        BigInteger,
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    transaction_date = Column(Date, nullable=False, index=True)
    ticker = Column(
        Text,
        ForeignKey("asset_master.ticker"),
        nullable=False,
        index=True,
    )
    transaction_type = Column(Text, nullable=False)
    quantity = Column(Numeric, nullable=False, default=0)
    price = Column(Numeric, nullable=False, default=0)
    fee = Column(Numeric, nullable=False, default=0)
    tax = Column(Numeric, nullable=False, default=0)
    memo = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now)


class Dividend(Base):
    __tablename__ = "dividends"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(
        BigInteger,
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dividend_date = Column(Date, nullable=False, index=True)
    ticker = Column(
        Text,
        ForeignKey("asset_master.ticker"),
        nullable=False,
        index=True,
    )
    currency = Column(Text, nullable=False)
    gross_amount = Column(Numeric, nullable=False, default=0)
    tax = Column(Numeric, nullable=False, default=0)
    net_amount = Column(Numeric, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=datetime.now)


class Price(Base):
    __tablename__ = "prices"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    price_date = Column(Date, nullable=False, index=True)
    ticker = Column(
        Text,
        ForeignKey("asset_master.ticker"),
        nullable=False,
        index=True,
    )
    open_price = Column(Numeric, nullable=False, default=0)
    high_price = Column(Numeric, nullable=False, default=0)
    low_price = Column(Numeric, nullable=False, default=0)
    close_price = Column(Numeric, nullable=False, default=0)
    nav = Column(Numeric, nullable=True)
    volume = Column(BigInteger, nullable=False, default=0)
    trading_value = Column(Numeric, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=datetime.now)

    __table_args__ = (
        UniqueConstraint("price_date", "ticker"),
    )


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    rate_date = Column(Date, nullable=False)
    from_currency = Column(Text, nullable=False)
    to_currency = Column(Text, nullable=False)
    rate = Column(Numeric, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.now)

    __table_args__ = (
        UniqueConstraint("rate_date", "from_currency", "to_currency"),
    )


class InvestmentProfile(Base):
    __tablename__ = "investment_profiles"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(
        UUID(as_uuid=True),        
        nullable=False,
        unique=True,
    )
    risk_profile = Column(Text, nullable=False, default="balanced")
    investment_horizon_years = Column(Integer, nullable=True)
    target_return = Column(Numeric, nullable=True)
    max_drawdown = Column(Numeric, nullable=True)
    monthly_investment = Column(Numeric, nullable=False, default=0)
    preferred_markets = Column(ARRAY(Text), nullable=False, default=list)
    excluded_assets = Column(ARRAY(Text), nullable=False, default=list)
    ai_advice_enabled = Column(Boolean, nullable=False, default=True)
    ai_advice_style = Column(Text, nullable=False, default="balanced")
    memo = Column(Text, nullable=True)
    investment_preference_text = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now)


class Watchlist(Base):
    __tablename__ = "watchlists"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(
        UUID(as_uuid=True),        
        nullable=False,
    )
    ticker = Column(
        Text,
        ForeignKey("asset_master.ticker"),
        nullable=False,
    )
    memo = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)

    __table_args__ = (
        UniqueConstraint("user_id", "ticker"),
    )


class News(Base):
    __tablename__ = "news"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    title = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    url = Column(Text, nullable=False, unique=True)
    source_name = Column(Text, nullable=True)
    ticker = Column(
        Text,
        ForeignKey("asset_master.ticker"),
        nullable=True,
    )
    market = Column(Text, nullable=True)
    language = Column(Text, default="ko")
    created_at = Column(DateTime(timezone=True), default=datetime.now)


class UserSetting(Base):
    __tablename__ = "user_settings"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(
        UUID(as_uuid=True),        
        nullable=False,
        unique=True,
    )
    morning_report_enabled = Column(Boolean, nullable=False, default=True)
    morning_report_time = Column(Time, nullable=False)
    kakao_enabled = Column(Boolean, nullable=False, default=False)
    news_enabled = Column(Boolean, nullable=False, default=True)
    ai_advice_enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now)

class RecommendationLog(Base):
    __tablename__ = "recommendation_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(
        UUID(as_uuid=True),        
        nullable=False,
        index=True,
    )
    recommendation_date = Column(Date, nullable=False, index=True)
    ticker = Column(
        Text,
        ForeignKey("asset_master.ticker"),
        nullable=False,
    )
    name = Column(Text, nullable=True)
    target_weight = Column(Numeric, nullable=False, default=0)
    current_weight = Column(Numeric, nullable=False, default=0)
    weight_gap = Column(Numeric, nullable=False, default=0)
    recent_high = Column(Numeric, nullable=False, default=0)
    current_price = Column(Numeric, nullable=False, default=0)
    drawdown = Column(Numeric, nullable=False, default=0)
    drawdown_score = Column(Integer, nullable=False, default=0)
    priority_score = Column(Numeric, nullable=False, default=0)
    recommended_buy = Column(Numeric, nullable=False, default=0)
    expected_weight_after = Column(Numeric, nullable=False, default=0)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
