"""
database/repository.py

PostgreSQL/Supabase 데이터베이스 접근 및 CRUD 함수를 제공합니다.

- 가격 데이터 저장 및 조회
- 계좌 및 목표 비중 관리
- 거래내역 및 분배금 관리
- 매수 추천 결과 기록 및 조회
- 자산 마스터 관리 및 검색
- 사용자별 데이터 분리
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from core.config import ETFConfig, load_config
from database.connection import get_db_session, init_db
from database.models import (
    Account,
    AccountTarget,
    AssetMaster,
    Dividend,
    InvestmentProfile,
    Price,
    RecommendationLog,
    Transaction,
    UserSetting,
    Watchlist,
)

class Repository:
    def __init__(self, user_id: Optional[str] = None):
        init_db()
        self.user_id = user_id

    # -------------------------------------------------------------
    # 가격 데이터 (Price) 관리
    # -------------------------------------------------------------

    def upsert_prices(
        self,
        price_dicts: List[Dict[str, Any]],
    ) -> int:
        """
        가격 목록을 삽입하거나 기존 데이터가 있으면 갱신합니다.
        성공적으로 처리된 행 개수를 반환합니다.
        """
        if not price_dicts:
            return 0

        saved_count = 0

        with get_db_session() as session:
            for item in price_dicts:
                date_str = str(
                    item.get("date", "")
                ).replace("-", "")

                ticker = str(
                    item.get("ticker", "")
                ).strip()

                if not date_str or not ticker:
                    continue

                price_date = datetime.strptime(
                    date_str,
                    "%Y%m%d",
                ).date()

                existing = (
                    session.query(Price)
                    .filter(
                        Price.price_date == price_date,
                        Price.ticker == ticker,
                    )
                    .first()
                )

                if existing:
                    existing.open_price = float(
                        item.get(
                            "open_price",
                            existing.open_price or 0,
                        )
                    )

                    existing.high_price = float(
                        item.get(
                            "high_price",
                            existing.high_price or 0,
                        )
                    )

                    existing.low_price = float(
                        item.get(
                            "low_price",
                            existing.low_price or 0,
                        )
                    )

                    existing.close_price = float(
                        item.get(
                            "close_price",
                            existing.close_price or 0,
                        )
                    )

                    existing.nav = float(
                        item.get(
                            "nav",
                            existing.nav or 0,
                        )
                    )

                    existing.volume = int(
                        item.get(
                            "volume",
                            existing.volume or 0,
                        )
                    )

                    existing.trading_value = float(
                        item.get(
                            "trading_value",
                            existing.trading_value or 0,
                        )
                    )

                else:
                    new_price = Price(
                        price_date=price_date,
                        ticker=ticker,
                        open_price=float(
                            item.get("open_price", 0.0)
                        ),
                        high_price=float(
                            item.get("high_price", 0.0)
                        ),
                        low_price=float(
                            item.get("low_price", 0.0)
                        ),
                        close_price=float(
                            item.get("close_price", 0.0)
                        ),
                        nav=float(
                            item.get("nav", 0.0)
                        ),
                        volume=int(
                            item.get("volume", 0)
                        ),
                        trading_value=float(
                            item.get("trading_value", 0.0)
                        ),
                    )

                    session.add(new_price)

                saved_count += 1

        return saved_count

    def get_prices(
        self,
        ticker: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Price]:
        """
        특정 종목의 가격 이력을 조회합니다.

        - start_date: YYYYMMDD 또는 YYYY-MM-DD
        - end_date: YYYYMMDD 또는 YYYY-MM-DD
        - limit: 조건에 해당하는 데이터 중 최신 N개
        - 반환 순서: 날짜 오름차순
        - 종가가 0 이하인 데이터는 제외
        """
        clean_ticker = str(ticker).strip()

        if not clean_ticker:
            return []

        with get_db_session() as session:
            query = session.query(Price).filter(
                Price.ticker == clean_ticker,
                Price.close_price > 0,
            )

            if start_date:
                start_dt = datetime.strptime(
                    str(start_date).replace("-", ""),
                    "%Y%m%d",
                ).date()

                query = query.filter(
                    Price.price_date >= start_dt
                )

            if end_date:
                end_dt = datetime.strptime(
                    str(end_date).replace("-", ""),
                    "%Y%m%d",
                ).date()

                query = query.filter(
                    Price.price_date <= end_dt
                )

            if limit is not None:
                safe_limit = int(limit)

                if safe_limit <= 0:
                    return []

                prices = list(
                    query.order_by(
                        Price.price_date.desc()
                    )
                    .limit(safe_limit)
                    .all()
                )

                prices.reverse()

                return prices

            return list(
                query.order_by(
                    Price.price_date.asc()
                ).all()
            )

    def get_latest_price(
        self,
        ticker: str,
    ) -> Optional[Price]:
        """특정 종목의 가장 최신 유효 가격을 조회합니다."""
        clean_ticker = str(ticker).strip()

        if not clean_ticker:
            return None

        with get_db_session() as session:
            return (
                session.query(Price)
                .filter(
                    Price.ticker == clean_ticker,
                    Price.close_price > 0,
                )
                .order_by(
                    Price.price_date.desc()
                )
                .first()
            )

    def get_recent_3m_high(
        self,
        ticker: str,
        as_of_date: Optional[str] = None,
        exclude_today: bool = False,
    ) -> Tuple[float, str]:
        """
        최근 약 3개월 최고 종가와 발생일을 반환합니다.

        exclude_today=True이면 기준일 가격은 제외합니다.
        """
        clean_ticker = str(ticker).strip()

        if not clean_ticker:
            return (0.0, "")

        with get_db_session() as session:
            latest = (
                session.query(Price)
                .filter(
                    Price.ticker == clean_ticker,
                    Price.close_price > 0,
                )
                .order_by(
                    Price.price_date.desc()
                )
                .first()
            )

            if not latest:
                return (0.0, "")

            if as_of_date:
                ref_date = datetime.strptime(
                    str(as_of_date).replace("-", ""),
                    "%Y%m%d",
                ).date()
            else:
                ref_date = latest.price_date

            start_date = (
                ref_date - timedelta(days=93)
            )

            query = session.query(Price).filter(
                Price.ticker == clean_ticker,
                Price.close_price > 0,
                Price.price_date >= start_date,
            )

            if exclude_today:
                query = query.filter(
                    Price.price_date < ref_date
                )
            else:
                query = query.filter(
                    Price.price_date <= ref_date
                )

            high_row = (
                query.order_by(
                    Price.close_price.desc(),
                    Price.price_date.desc(),
                )
                .first()
            )

            if high_row:
                return (
                    float(high_row.close_price),
                    high_row.price_date.strftime(
                        "%Y%m%d"
                    ),
                )

            return (
                float(latest.close_price),
                latest.price_date.strftime(
                    "%Y%m%d"
                ),
            )

    # -------------------------------------------------------------
    # 계좌 (Account) 관리
    # -------------------------------------------------------------

    def get_accounts(self) -> List[Account]:
        """현재 사용자의 모든 계좌를 조회합니다."""
        if not self.user_id:
            return []

        with get_db_session() as session:
            return list(
                session.query(Account)
                .filter(
                    Account.user_id == self.user_id
                )
                .order_by(
                    Account.is_default.desc(),
                    Account.id.asc(),
                )
                .all()
            )

    def get_account(
        self,
        account_id: int,
    ) -> Optional[Account]:
        """현재 사용자의 특정 계좌를 조회합니다."""
        if not self.user_id:
            return None

        with get_db_session() as session:
            return (
                session.query(Account)
                .filter(
                    Account.id == account_id,
                    Account.user_id == self.user_id,
                )
                .first()
            )

    def get_default_account(
        self,
    ) -> Optional[Account]:
        """현재 사용자의 기본 계좌를 조회합니다."""
        if not self.user_id:
            return None

        with get_db_session() as session:
            account = (
                session.query(Account)
                .filter(
                    Account.user_id == self.user_id,
                    Account.is_default.is_(True),
                )
                .order_by(
                    Account.id.asc()
                )
                .first()
            )

            if account:
                return account

            return (
                session.query(Account)
                .filter(
                    Account.user_id == self.user_id
                )
                .order_by(
                    Account.id.asc()
                )
                .first()
            )

    def create_account(
        self,
        account_name: str,
        account_number: str = "",
        broker: str = "",
        initial_capital: float = 0.0,
        base_monthly: float = 0.0,
        max_additional_monthly: float = 0.0,
        buy_cycle_type: str = "monthly",
        buy_cycle_detail: str = "25",
        currency: str = "KRW",
        account_type: str = "brokerage",
        market_scope: str = "KR",
        contribution_type: str = "none",
        contribution_amount: float = 0.0,
        contribution_month: Optional[int] = None,
        strategy_type: str = "allocation",
        is_default: int = 0,
        memo: str = "",
    ) -> Account:
        """
        현재 사용자의 신규 계좌를 생성합니다.

        사용자의 첫 번째 계좌는 자동으로
        기본 계좌가 됩니다.

        계좌 생성과 목표 종목 등록은 분리합니다.
        """

        if not self.user_id:
            raise ValueError(
                "계좌를 생성하려면 "
                "user_id가 필요합니다."
            )

        clean_account_name = str(
            account_name
        ).strip()

        if not clean_account_name:
            raise ValueError(
                "계좌 이름을 입력해야 합니다."
            )

        clean_currency = str(
            currency or "KRW"
        ).strip().upper()

        if clean_currency not in (
            "KRW",
            "USD",
        ):
            raise ValueError(
                "지원하지 않는 계좌 통화입니다."
            )

        clean_account_type = str(
            account_type or "brokerage"
        ).strip().lower()

        clean_market_scope = str(
            market_scope or "KR"
        ).strip().upper()

        clean_contribution_type = str(
            contribution_type or "none"
        ).strip().lower()

        if clean_contribution_type not in (
            "none",
            "monthly",
            "yearly",
            "irregular",
        ):
            raise ValueError(
                "지원하지 않는 자금 납입 방식입니다."
            )

        clean_strategy_type = str(
            strategy_type or "allocation"
        ).strip().lower()

        if clean_strategy_type not in (
            "allocation",
            "trading",
            "mixed",
        ):
            raise ValueError(
                "지원하지 않는 계좌 운용 방식입니다."
            )

        clean_contribution_month = None

        if contribution_month is not None:
            clean_contribution_month = int(
                contribution_month
            )

            if not 1 <= clean_contribution_month <= 12:
                raise ValueError(
                    "납입 월은 1~12 사이여야 합니다."
                )

        if (
            clean_contribution_type != "yearly"
        ):
            clean_contribution_month = None

        with get_db_session() as session:
            existing_account_count = (
                session.query(Account)
                .filter(
                    Account.user_id
                    == self.user_id
                )
                .count()
            )

            make_default = (
                bool(is_default)
                or existing_account_count == 0
            )

            if make_default:
                (
                    session.query(Account)
                    .filter(
                        Account.user_id
                        == self.user_id
                    )
                    .update(
                        {
                            Account.is_default:
                                False
                        }
                    )
                )

            account = Account(
                user_id=self.user_id,

                account_name=
                    clean_account_name,

                account_number=str(
                    account_number or ""
                ).strip(),

                broker=str(
                    broker or ""
                ).strip(),

                initial_capital=float(
                    initial_capital or 0
                ),

                base_monthly=float(
                    base_monthly or 0
                ),

                max_additional_monthly=float(
                    max_additional_monthly or 0
                ),

                buy_cycle_type=(
                    str(
                        buy_cycle_type
                        or "monthly"
                    )
                    .strip()
                    .lower()
                ),

                buy_cycle_detail=str(
                    buy_cycle_detail or "25"
                ).strip(),

                currency=clean_currency,

                account_type=
                    clean_account_type,

                market_scope=
                    clean_market_scope,

                contribution_type=
                    clean_contribution_type,

                contribution_amount=float(
                    contribution_amount or 0
                ),

                contribution_month=
                    clean_contribution_month,

                strategy_type=
                    clean_strategy_type,

                is_default=make_default,

                memo=str(
                    memo or ""
                ).strip(),
            )

            session.add(account)
            session.flush()
            session.refresh(account)

            return account

    def update_account(
        self,
        account_id: int,
        account_name: str,
        account_number: str = "",
        broker: str = "",
        initial_capital: float = 0.0,
        base_monthly: float = 0.0,
        max_additional_monthly: float = 0.0,
        buy_cycle_type: str = "monthly",
        buy_cycle_detail: str = "25",
        currency: str = "KRW",
        account_type: str = "brokerage",
        market_scope: str = "KR",
        contribution_type: str = "none",
        contribution_amount: float = 0.0,
        contribution_month: Optional[int] = None,
        strategy_type: str = "allocation",
        is_default: int = 0,
        memo: str = "",
    ) -> bool:
        """현재 사용자의 계좌 정보를 수정합니다."""

        if not self.user_id:
            return False

        clean_account_name = str(
            account_name
        ).strip()

        if not clean_account_name:
            raise ValueError(
                "계좌 이름을 입력해야 합니다."
            )

        clean_currency = str(
            currency or "KRW"
        ).strip().upper()

        if clean_currency not in (
            "KRW",
            "USD",
        ):
            raise ValueError(
                "지원하지 않는 계좌 통화입니다."
            )

        clean_account_type = str(
            account_type or "brokerage"
        ).strip().lower()

        clean_market_scope = str(
            market_scope or "KR"
        ).strip().upper()

        clean_contribution_type = str(
            contribution_type or "none"
        ).strip().lower()

        if clean_contribution_type not in (
            "none",
            "monthly",
            "yearly",
            "irregular",
        ):
            raise ValueError(
                "지원하지 않는 자금 납입 방식입니다."
            )

        clean_strategy_type = str(
            strategy_type or "allocation"
        ).strip().lower()

        if clean_strategy_type not in (
            "allocation",
            "trading",
            "mixed",
        ):
            raise ValueError(
                "지원하지 않는 계좌 운용 방식입니다."
            )

        clean_contribution_month = None

        if contribution_month is not None:
            clean_contribution_month = int(
                contribution_month
            )

            if not 1 <= clean_contribution_month <= 12:
                raise ValueError(
                    "납입 월은 1~12 사이여야 합니다."
                )

        if (
            clean_contribution_type != "yearly"
        ):
            clean_contribution_month = None

        with get_db_session() as session:
            account = (
                session.query(Account)
                .filter(
                    Account.id == account_id,
                    Account.user_id
                    == self.user_id,
                )
                .first()
            )

            if not account:
                return False

            if is_default:
                (
                    session.query(Account)
                    .filter(
                        Account.user_id
                        == self.user_id,
                        Account.id
                        != account_id,
                    )
                    .update(
                        {
                            Account.is_default:
                                False
                        }
                    )
                )

            account.account_name = (
                clean_account_name
            )

            account.account_number = str(
                account_number or ""
            ).strip()

            account.broker = str(
                broker or ""
            ).strip()

            account.initial_capital = float(
                initial_capital or 0
            )

            account.base_monthly = float(
                base_monthly or 0
            )

            account.max_additional_monthly = float(
                max_additional_monthly or 0
            )

            account.buy_cycle_type = (
                str(
                    buy_cycle_type
                    or "monthly"
                )
                .strip()
                .lower()
            )

            account.buy_cycle_detail = str(
                buy_cycle_detail or "25"
            ).strip()

            account.currency = (
                clean_currency
            )

            account.account_type = (
                clean_account_type
            )

            account.market_scope = (
                clean_market_scope
            )

            account.contribution_type = (
                clean_contribution_type
            )

            account.contribution_amount = float(
                contribution_amount or 0
            )

            account.contribution_month = (
                clean_contribution_month
            )

            account.strategy_type = (
                clean_strategy_type
            )

            account.is_default = bool(
                is_default
            )

            account.memo = str(
                memo or ""
            ).strip()

            account.updated_at = datetime.now()

            return True
    def set_default_account(
        self,
        account_id: int,
    ) -> bool:
        """현재 사용자의 계좌를 기본 계좌로 지정합니다."""
        if not self.user_id:
            return False

        with get_db_session() as session:
            account = (
                session.query(Account)
                .filter(
                    Account.id == account_id,
                    Account.user_id == self.user_id,
                )
                .first()
            )

            if not account:
                return False

            (
                session.query(Account)
                .filter(
                    Account.user_id == self.user_id
                )
                .update(
                    {
                        Account.is_default: False
                    }
                )
            )

            account.is_default = True

            return True

    def delete_account(
        self,
        account_id: int,
    ) -> bool:
        """현재 사용자의 계좌를 삭제합니다."""
        if not self.user_id:
            return False

        with get_db_session() as session:
            account = (
                session.query(Account)
                .filter(
                    Account.id == account_id,
                    Account.user_id == self.user_id,
                )
                .first()
            )

            if not account:
                return False

            was_default = bool(
                account.is_default
            )

            session.delete(account)
            session.flush()

            if was_default:
                remaining = (
                    session.query(Account)
                    .filter(
                        Account.user_id
                        == self.user_id
                    )
                    .order_by(
                        Account.id.asc()
                    )
                    .first()
                )

                if remaining:
                    remaining.is_default = True

            return True

    # -------------------------------------------------------------
    # 계좌 목표 비중 (AccountTarget) 관리
    # -------------------------------------------------------------

    def get_account_targets(
        self,
        account_id: Optional[int] = None,
    ) -> List[ETFConfig]:
        """
        현재 사용자의 계좌별 목표 비중을 반환합니다.

        account_id가 지정되면 해당 계좌만 반환하고,
        None이면 모든 계좌 목표 비중을 초기 자본금 비율로 통합합니다.
        """
        if not self.user_id:
            return []

        with get_db_session() as session:
            # -----------------------------------------------------
            # 특정 계좌
            # -----------------------------------------------------
            if account_id is not None:
                account = (
                    session.query(Account)
                    .filter(
                        Account.id == account_id,
                        Account.user_id
                        == self.user_id,
                    )
                    .first()
                )

                if not account:
                    return []

                rows = (
                    session.query(
                        AccountTarget,
                        AssetMaster,
                    )
                    .join(
                        AssetMaster,
                        AssetMaster.ticker
                        == AccountTarget.ticker,
                    )
                    .filter(
                        AccountTarget.account_id
                        == account_id
                    )
                    .order_by(
                        AccountTarget.id.asc()
                    )
                    .all()
                )

                if rows:
                    return [
                        ETFConfig(
                            ticker=target.ticker,
                            name=asset.name,
                            target_weight=float(
                                target.target_weight
                                or 0
                            ),
                            dividend_yield=float(
                                target.dividend_yield
                                or 0
                            ),
                        )
                        for target, asset in rows
                    ]

                return list(
                    load_config().etfs
                )

            # -----------------------------------------------------
            # 현재 사용자의 모든 계좌
            # -----------------------------------------------------
            accounts = (
                session.query(Account)
                .filter(
                    Account.user_id
                    == self.user_id
                )
                .order_by(
                    Account.id.asc()
                )
                .all()
            )

            if not accounts:
                return list(
                    load_config().etfs
                )

            # -----------------------------------------------------
            # 계좌가 하나뿐인 경우
            # -----------------------------------------------------
            if len(accounts) == 1:
                rows = (
                    session.query(
                        AccountTarget,
                        AssetMaster,
                    )
                    .join(
                        AssetMaster,
                        AssetMaster.ticker
                        == AccountTarget.ticker,
                    )
                    .filter(
                        AccountTarget.account_id
                        == accounts[0].id
                    )
                    .order_by(
                        AccountTarget.id.asc()
                    )
                    .all()
                )

                if rows:
                    return [
                        ETFConfig(
                            ticker=target.ticker,
                            name=asset.name,
                            target_weight=float(
                                target.target_weight
                                or 0
                            ),
                            dividend_yield=float(
                                target.dividend_yield
                                or 0
                            ),
                        )
                        for target, asset in rows
                    ]

                return list(
                    load_config().etfs
                )

            # -----------------------------------------------------
            # 여러 계좌의 목표 비중 통합
            # -----------------------------------------------------
            total_capital = sum(
                max(
                    0.0,
                    float(
                        account.initial_capital
                        or 0
                    ),
                )
                for account in accounts
            )

            combined: Dict[
                str,
                Dict[str, Any],
            ] = {}

            for account in accounts:
                capital = max(
                    0.0,
                    float(
                        account.initial_capital
                        or 0
                    ),
                )

                if total_capital > 0:
                    weight_factor = (
                        capital
                        / total_capital
                    )
                else:
                    weight_factor = (
                        1.0
                        / len(accounts)
                    )

                rows = (
                    session.query(
                        AccountTarget,
                        AssetMaster,
                    )
                    .join(
                        AssetMaster,
                        AssetMaster.ticker
                        == AccountTarget.ticker,
                    )
                    .filter(
                        AccountTarget.account_id
                        == account.id
                    )
                    .order_by(
                        AccountTarget.id.asc()
                    )
                    .all()
                )

                if rows:
                    targets = [
                        (
                            target.ticker,
                            asset.name,
                            float(
                                target.target_weight
                                or 0
                            ),
                            float(
                                target.dividend_yield
                                or 0
                            ),
                        )
                        for target, asset in rows
                    ]

                else:
                    targets = [
                        (
                            etf.ticker,
                            etf.name,
                            float(
                                etf.target_weight
                                or 0
                            ),
                            float(
                                etf.dividend_yield
                                or 0
                            ),
                        )
                        for etf
                        in load_config().etfs
                    ]

                for (
                    ticker,
                    name,
                    target_weight,
                    dividend_yield,
                ) in targets:
                    if ticker not in combined:
                        combined[ticker] = {
                            "ticker": ticker,
                            "name": name,
                            "target_weight": 0.0,
                            "dividend_yield": 0.0,
                        }

                    combined[ticker][
                        "target_weight"
                    ] += (
                        target_weight
                        * weight_factor
                    )

                    combined[ticker][
                        "dividend_yield"
                    ] += (
                        dividend_yield
                        * weight_factor
                    )

            return [
                ETFConfig(
                    ticker=info["ticker"],
                    name=info["name"],
                    target_weight=round(
                        info["target_weight"],
                        6,
                    ),
                    dividend_yield=round(
                        info["dividend_yield"],
                        6,
                    ),
                )
                for info in combined.values()
            ]

    def save_account_targets(
        self,
        account_id: int,
        targets: List[ETFConfig],
    ) -> None:
        """현재 사용자의 계좌 목표 비중 목록을 저장합니다."""
        if not self.user_id:
            raise ValueError(
                "목표 비중을 저장하려면 user_id가 필요합니다."
            )

        with get_db_session() as session:
            account = (
                session.query(Account)
                .filter(
                    Account.id == account_id,
                    Account.user_id == self.user_id,
                )
                .first()
            )

            if not account:
                raise ValueError(
                    "현재 사용자의 계좌를 찾을 수 없습니다."
                )

            # 현재 단계의 ETFConfig에는 시장/통화 정보가 없으므로
            # 새 종목은 기존 국내 ETF 기본값으로 등록합니다.
            # 미국 종목 지원 단계에서 이 구조를 확장합니다.
            for target in targets:
                ticker = str(
                    target.ticker
                ).strip()

                asset = (
                    session.query(AssetMaster)
                    .filter(
                        AssetMaster.ticker == ticker
                    )
                    .first()
                )

                if not asset:
                    session.add(
                        AssetMaster(
                            ticker=ticker,
                            name=target.name,
                            market="KR",
                            exchange="KRX",
                            asset_type="ETF",
                            currency="KRW",
                            is_active=True,
                        )
                    )

            session.flush()

            (
                session.query(AccountTarget)
                .filter(
                    AccountTarget.account_id
                    == account_id
                )
                .delete()
            )

            for target in targets:
                session.add(
                    AccountTarget(
                        account_id=account_id,
                        ticker=str(
                            target.ticker
                        ).strip(),
                        target_weight=float(
                            target.target_weight
                            or 0
                        ),
                        dividend_yield=float(
                            target.dividend_yield
                            or 0
                        ),
                    )
                )

    # -------------------------------------------------------------
    # 거래내역 (Transaction) 관리
    # -------------------------------------------------------------

    def add_transaction(
        self,
        transaction_date: str,
        ticker: str,
        transaction_type: str,
        quantity: float,
        price: float,
        fee: float = 0.0,
        tax: float = 0.0,
        memo: str = "",
        account_id: Optional[int] = None,
    ) -> Transaction:
        """현재 사용자의 거래 내역을 추가합니다."""
        if not self.user_id:
            raise ValueError(
                "거래를 저장하려면 user_id가 필요합니다."
            )

        clean_ticker = str(
            ticker
        ).strip()

        tx_type = str(
            transaction_type
        ).upper().strip()

        if tx_type not in (
            "BUY",
            "SELL",
        ):
            raise ValueError(
                "거래 유형은 BUY 또는 SELL이어야 합니다."
            )

        clean_quantity = float(
            quantity
        )

        if clean_quantity <= 0:
            raise ValueError(
                "거래 수량은 0보다 커야 합니다."
            )

        clean_price = float(
            price
        )

        if clean_price < 0:
            raise ValueError(
                "거래 가격은 0 이상이어야 합니다."
            )

        tx_date = datetime.strptime(
            str(transaction_date).replace(
                "-",
                "",
            ),
            "%Y%m%d",
        ).date()

        with get_db_session() as session:
            if account_id is None:
                account = (
                    session.query(Account)
                    .filter(
                        Account.user_id
                        == self.user_id,
                        Account.is_default.is_(
                            True
                        ),
                    )
                    .order_by(
                        Account.id.asc()
                    )
                    .first()
                )

                if not account:
                    account = (
                        session.query(Account)
                        .filter(
                            Account.user_id
                            == self.user_id
                        )
                        .order_by(
                            Account.id.asc()
                        )
                        .first()
                    )

            else:
                account = (
                    session.query(Account)
                    .filter(
                        Account.id == account_id,
                        Account.user_id
                        == self.user_id,
                    )
                    .first()
                )

            if not account:
                raise ValueError(
                    "거래를 저장할 계좌를 찾을 수 없습니다."
                )

            asset = (
                session.query(AssetMaster)
                .filter(
                    AssetMaster.ticker
                    == clean_ticker
                )
                .first()
            )

            if not asset:
                raise ValueError(
                    "asset_master에 등록되지 않은 "
                    f"종목입니다: {clean_ticker}"
                )

            transaction = Transaction(
                account_id=account.id,
                transaction_date=tx_date,
                ticker=clean_ticker,
                transaction_type=tx_type,
                quantity=clean_quantity,
                price=clean_price,
                fee=float(fee or 0),
                tax=float(tax or 0),
                memo=str(
                    memo or ""
                ).strip(),
            )

            session.add(transaction)
            session.flush()
            session.refresh(transaction)

            return transaction

    def get_transactions(
        self,
        ticker: Optional[str] = None,
        account_id: Optional[int] = None,
    ) -> List[Transaction]:
        """현재 사용자의 거래 내역을 조회합니다."""
        if not self.user_id:
            return []

        with get_db_session() as session:
            query = (
                session.query(Transaction)
                .join(
                    Account,
                    Transaction.account_id
                    == Account.id,
                )
                .filter(
                    Account.user_id
                    == self.user_id
                )
            )

            if ticker:
                query = query.filter(
                    Transaction.ticker
                    == str(ticker).strip()
                )

            if account_id is not None:
                query = query.filter(
                    Transaction.account_id
                    == account_id
                )

            return list(
                query.order_by(
                    Transaction.transaction_date.asc(),
                    Transaction.id.asc(),
                )
                .all()
            )

    def update_transaction(
        self,
        tx_id: int,
        transaction_date: str,
        ticker: str,
        transaction_type: str,
        quantity: float,
        price: float,
        fee: float = 0.0,
        tax: float = 0.0,
        memo: str = "",
        account_id: Optional[int] = None,
    ) -> bool:
        """현재 사용자의 거래 내역을 수정합니다."""
        if not self.user_id:
            return False

        clean_ticker = str(
            ticker
        ).strip()

        tx_type = str(
            transaction_type
        ).upper().strip()

        if tx_type not in (
            "BUY",
            "SELL",
        ):
            raise ValueError(
                "거래 유형은 BUY 또는 SELL이어야 합니다."
            )

        clean_quantity = float(
            quantity
        )

        if clean_quantity <= 0:
            raise ValueError(
                "거래 수량은 0보다 커야 합니다."
            )

        clean_price = float(
            price
        )

        if clean_price < 0:
            raise ValueError(
                "거래 가격은 0 이상이어야 합니다."
            )

        tx_date = datetime.strptime(
            str(transaction_date).replace(
                "-",
                "",
            ),
            "%Y%m%d",
        ).date()

        with get_db_session() as session:
            transaction = (
                session.query(Transaction)
                .join(
                    Account,
                    Transaction.account_id
                    == Account.id,
                )
                .filter(
                    Transaction.id == tx_id,
                    Account.user_id
                    == self.user_id,
                )
                .first()
            )

            if not transaction:
                return False

            asset = (
                session.query(AssetMaster)
                .filter(
                    AssetMaster.ticker
                    == clean_ticker
                )
                .first()
            )

            if not asset:
                raise ValueError(
                    "asset_master에 등록되지 않은 "
                    f"종목입니다: {clean_ticker}"
                )

            if account_id is not None:
                new_account = (
                    session.query(Account)
                    .filter(
                        Account.id == account_id,
                        Account.user_id
                        == self.user_id,
                    )
                    .first()
                )

                if not new_account:
                    raise ValueError(
                        "변경할 계좌를 찾을 수 없습니다."
                    )

                transaction.account_id = (
                    new_account.id
                )

            transaction.transaction_date = (
                tx_date
            )

            transaction.ticker = (
                clean_ticker
            )

            transaction.transaction_type = (
                tx_type
            )

            transaction.quantity = (
                clean_quantity
            )

            transaction.price = (
                clean_price
            )

            transaction.fee = float(
                fee or 0
            )

            transaction.tax = float(
                tax or 0
            )

            transaction.memo = str(
                memo or ""
            ).strip()

            transaction.updated_at = (
                datetime.now()
            )

            return True

    def delete_transaction(
        self,
        tx_id: int,
    ) -> bool:
        """현재 사용자의 거래 내역을 삭제합니다."""
        if not self.user_id:
            return False

        with get_db_session() as session:
            transaction = (
                session.query(Transaction)
                .join(
                    Account,
                    Transaction.account_id
                    == Account.id,
                )
                .filter(
                    Transaction.id == tx_id,
                    Account.user_id
                    == self.user_id,
                )
                .first()
            )

            if not transaction:
                return False

            session.delete(transaction)

            return True

    # -------------------------------------------------------------
    # 분배금 / 배당금 (Dividend) 관리
    # -------------------------------------------------------------

    def add_dividend(
        self,
        dividend_date: str,
        ticker: str,
        gross_amount: float,
        tax: float = 0.0,
        net_amount: Optional[float] = None,
        account_id: Optional[int] = None,
    ) -> Dividend:
        """현재 사용자의 분배금/배당금 내역을 추가합니다."""
        if not self.user_id:
            raise ValueError(
                "분배금을 저장하려면 user_id가 필요합니다."
            )

        clean_ticker = str(
            ticker
        ).strip()

        div_date = datetime.strptime(
            str(dividend_date).replace(
                "-",
                "",
            ),
            "%Y%m%d",
        ).date()

        gross = float(
            gross_amount or 0
        )

        tax_value = float(
            tax or 0
        )

        if net_amount is None:
            net = (
                gross
                - tax_value
            )
        else:
            net = float(
                net_amount
            )

        with get_db_session() as session:
            if account_id is None:
                account = (
                    session.query(Account)
                    .filter(
                        Account.user_id
                        == self.user_id,
                        Account.is_default.is_(
                            True
                        ),
                    )
                    .order_by(
                        Account.id.asc()
                    )
                    .first()
                )

                if not account:
                    account = (
                        session.query(Account)
                        .filter(
                            Account.user_id
                            == self.user_id
                        )
                        .order_by(
                            Account.id.asc()
                        )
                        .first()
                    )

            else:
                account = (
                    session.query(Account)
                    .filter(
                        Account.id == account_id,
                        Account.user_id
                        == self.user_id,
                    )
                    .first()
                )

            if not account:
                raise ValueError(
                    "분배금을 저장할 계좌를 찾을 수 없습니다."
                )

            asset = (
                session.query(AssetMaster)
                .filter(
                    AssetMaster.ticker
                    == clean_ticker
                )
                .first()
            )

            if not asset:
                raise ValueError(
                    "asset_master에 등록되지 않은 "
                    f"종목입니다: {clean_ticker}"
                )

            dividend = Dividend(
                account_id=account.id,
                dividend_date=div_date,
                ticker=clean_ticker,
                currency=asset.currency,
                gross_amount=gross,
                tax=tax_value,
                net_amount=net,
            )

            session.add(dividend)
            session.flush()
            session.refresh(dividend)

            return dividend

    def get_dividends(
        self,
        ticker: Optional[str] = None,
        account_id: Optional[int] = None,
    ) -> List[Dividend]:
        """현재 사용자의 분배금/배당금 내역을 조회합니다."""
        if not self.user_id:
            return []

        with get_db_session() as session:
            query = (
                session.query(Dividend)
                .join(
                    Account,
                    Dividend.account_id
                    == Account.id,
                )
                .filter(
                    Account.user_id
                    == self.user_id
                )
            )

            if ticker:
                query = query.filter(
                    Dividend.ticker
                    == str(ticker).strip()
                )

            if account_id is not None:
                query = query.filter(
                    Dividend.account_id
                    == account_id
                )

            return list(
                query.order_by(
                    Dividend.dividend_date.asc(),
                    Dividend.id.asc(),
                )
                .all()
            )

    # -------------------------------------------------------------
    # 매수 추천 기록 (RecommendationLog) 관리
    # -------------------------------------------------------------

    def save_recommendations(
        self,
        rec_list: List[Dict[str, Any]],
    ) -> None:
        """현재 사용자의 매수 추천 결과를 저장합니다."""
        if not self.user_id:
            raise ValueError(
                "추천 결과를 저장하려면 user_id가 필요합니다."
            )

        if not rec_list:
            return

        with get_db_session() as session:
            for item in rec_list:
                date_value = item.get(
                    "date",
                    datetime.now().strftime(
                        "%Y-%m-%d"
                    ),
                )

                if isinstance(
                    date_value,
                    datetime,
                ):
                    recommendation_date = (
                        date_value.date()
                    )

                elif (
                    hasattr(
                        date_value,
                        "year",
                    )
                    and hasattr(
                        date_value,
                        "month",
                    )
                    and hasattr(
                        date_value,
                        "day",
                    )
                ):
                    recommendation_date = (
                        date_value
                    )

                else:
                    recommendation_date = (
                        datetime.strptime(
                            str(
                                date_value
                            ).replace(
                                "-",
                                "",
                            ),
                            "%Y%m%d",
                        ).date()
                    )

                ticker = str(
                    item.get(
                        "ticker",
                        "",
                    )
                ).strip()

                if not ticker:
                    continue

                # recommendation_logs.ticker는 asset_master FK이므로
                # 추천 종목이 실제 자산 마스터에 존재하는지 확인합니다.
                asset = (
                    session.query(AssetMaster)
                    .filter(
                        AssetMaster.ticker
                        == ticker
                    )
                    .first()
                )

                if not asset:
                    raise ValueError(
                        "추천 종목이 asset_master에 "
                        f"등록되어 있지 않습니다: {ticker}"
                    )

                log = RecommendationLog(
                    user_id=self.user_id,
                    recommendation_date=(
                        recommendation_date
                    ),
                    ticker=ticker,
                    name=str(
                        item.get(
                            "name",
                            "",
                        )
                        or ""
                    ),
                    target_weight=float(
                        item.get(
                            "target_weight",
                            0.0,
                        )
                        or 0
                    ),
                    current_weight=float(
                        item.get(
                            "current_weight",
                            0.0,
                        )
                        or 0
                    ),
                    weight_gap=float(
                        item.get(
                            "weight_gap",
                            0.0,
                        )
                        or 0
                    ),
                    recent_high=float(
                        item.get(
                            "recent_high",
                            0.0,
                        )
                        or 0
                    ),
                    current_price=float(
                        item.get(
                            "current_price",
                            0.0,
                        )
                        or 0
                    ),
                    drawdown=float(
                        item.get(
                            "drawdown",
                            0.0,
                        )
                        or 0
                    ),
                    drawdown_score=int(
                        item.get(
                            "drawdown_score",
                            0,
                        )
                        or 0
                    ),
                    priority_score=float(
                        item.get(
                            "priority_score",
                            0.0,
                        )
                        or 0
                    ),
                    recommended_buy=float(
                        item.get(
                            "recommended_buy",
                            0.0,
                        )
                        or 0
                    ),
                    expected_weight_after=float(
                        item.get(
                            "expected_weight_after",
                            0.0,
                        )
                        or 0
                    ),
                    reason=str(
                        item.get(
                            "reason",
                            "",
                        )
                        or ""
                    ),
                )

                session.add(log)

    def get_latest_recommendations(
        self,
    ) -> List[RecommendationLog]:
        """현재 사용자의 가장 최근 매수 추천 결과를 조회합니다."""
        if not self.user_id:
            return []

        with get_db_session() as session:
            latest_date_row = (
                session.query(
                    RecommendationLog.recommendation_date
                )
                .filter(
                    RecommendationLog.user_id
                    == self.user_id
                )
                .order_by(
                    RecommendationLog.recommendation_date.desc()
                )
                .first()
            )

            if not latest_date_row:
                return []

            latest_date = (
                latest_date_row[0]
            )

            return list(
                session.query(
                    RecommendationLog
                )
                .filter(
                    RecommendationLog.user_id
                    == self.user_id,
                    RecommendationLog.recommendation_date
                    == latest_date,
                )
                .order_by(
                    RecommendationLog.id.asc()
                )
                .all()
            )

    # -------------------------------------------------------------
    # 자산 마스터 (AssetMaster) 관리 및 검색
    # -------------------------------------------------------------

    def save_etf_master(
        self,
        items: List[Dict[str, str]],
    ) -> int:
        """
        자산 마스터 정보를 저장하거나 갱신합니다.

        기존 코드와의 호환을 위해
        함수 이름은 save_etf_master를 유지합니다.
        """
        if not items:
            return 0

        saved = 0

        with get_db_session() as session:
            for item in items:
                ticker = str(
                    item.get(
                        "ticker",
                        "",
                    )
                ).strip()

                name = str(
                    item.get(
                        "name",
                        "",
                    )
                ).strip()

                if not ticker or not name:
                    continue

                market = str(
                    item.get("market")
                    or "KR"
                ).strip().upper()

                exchange = str(
                    item.get("exchange")
                    or "KRX"
                ).strip().upper()

                asset_type = str(
                    item.get("asset_type")
                    or "ETF"
                ).strip().upper()

                currency = str(
                    item.get("currency")
                    or "KRW"
                ).strip().upper()

                asset = (
                    session.query(AssetMaster)
                    .filter(
                        AssetMaster.ticker
                        == ticker
                    )
                    .first()
                )

                if asset:
                    asset.name = name
                    asset.market = market
                    asset.exchange = exchange
                    asset.asset_type = asset_type
                    asset.currency = currency
                    asset.is_active = True
                    asset.updated_at = (
                        datetime.now()
                    )

                else:
                    session.add(
                        AssetMaster(
                            ticker=ticker,
                            name=name,
                            market=market,
                            exchange=exchange,
                            asset_type=asset_type,
                            currency=currency,
                            is_active=True,
                        )
                    )

                saved += 1

        return saved

    def search_etf_master(
        self,
        keyword: str = "",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        종목코드 또는 종목명으로 활성 자산을 검색합니다.

        기존 코드와의 호환을 위해
        함수 이름은 search_etf_master를 유지합니다.
        """
        clean_keyword = str(
            keyword
        ).strip()

        safe_limit = max(
            1,
            min(
                int(limit),
                200,
            ),
        )

        with get_db_session() as session:
            query = (
                session.query(AssetMaster)
                .filter(
                    AssetMaster.is_active.is_(
                        True
                    )
                )
            )

            if clean_keyword:
                pattern = (
                    f"%{clean_keyword}%"
                )

                query = query.filter(
                    (
                        AssetMaster.ticker.ilike(
                            pattern
                        )
                    )
                    | (
                        AssetMaster.name.ilike(
                            pattern
                        )
                    )
                )

            results = (
                query.order_by(
                    AssetMaster.market.asc(),
                    AssetMaster.name.asc(),
                )
                .limit(
                    safe_limit
                )
                .all()
            )

            return [
                {
                    "ticker": asset.ticker,
                    "name": asset.name,
                    "market": asset.market,
                    "exchange": asset.exchange,
                    "asset_type": asset.asset_type,
                    "currency": asset.currency,
                }
                for asset in results
            ]

    def get_etf_master(
        self,
        ticker: str,
    ) -> Optional[AssetMaster]:
        """
        종목코드로 활성 자산 마스터 한 건을 조회합니다.

        기존 코드와의 호환을 위해
        함수 이름은 get_etf_master를 유지합니다.
        """
        clean_ticker = str(
            ticker
        ).strip()

        if not clean_ticker:
            return None

        with get_db_session() as session:
            return (
                session.query(AssetMaster)
                .filter(
                    AssetMaster.ticker
                    == clean_ticker,
                    AssetMaster.is_active.is_(
                        True
                    ),
                )
                .first()
            )

    # -------------------------------------------------------------
    # 투자 성향 (InvestmentProfile) 관리
    # -------------------------------------------------------------

    def get_investment_profile(
        self,
    ) -> Optional[InvestmentProfile]:
        """현재 사용자의 투자 성향을 조회합니다."""
        if not self.user_id:
            return None

        with get_db_session() as session:
            return (
                session.query(InvestmentProfile)
                .filter(
                    InvestmentProfile.user_id
                    == self.user_id
                )
                .first()
            )

    def save_investment_profile(
        self,
        risk_profile: str = "balanced",
        investment_horizon_years: Optional[int] = None,
        target_return: Optional[float] = None,
        max_drawdown: Optional[float] = None,
        monthly_investment: float = 0.0,
        preferred_markets: Optional[List[str]] = None,
        excluded_assets: Optional[List[str]] = None,
        ai_advice_enabled: bool = True,
        ai_advice_style: str = "balanced",
        memo: str = "",
        investment_preference_text: str = "",
    ) -> InvestmentProfile:
        """
        현재 사용자의 투자 성향을 저장합니다.

        이미 투자 성향이 존재하면 수정하고,
        없으면 새로 생성합니다.
        """
        if not self.user_id:
            raise ValueError(
                "투자 성향을 저장하려면 user_id가 필요합니다."
            )

        clean_risk_profile = str(
            risk_profile or "balanced"
        ).strip()

        clean_ai_advice_style = str(
            ai_advice_style or "balanced"
        ).strip()

        clean_preferred_markets = [
            str(value).strip()
            for value in (
                preferred_markets or []
            )
            if str(value).strip()
        ]

        clean_excluded_assets = [
            str(value).strip()
            for value in (
                excluded_assets or []
            )
            if str(value).strip()
        ]

        with get_db_session() as session:
            profile = (
                session.query(InvestmentProfile)
                .filter(
                    InvestmentProfile.user_id
                    == self.user_id
                )
                .first()
            )

            if profile is None:
                profile = InvestmentProfile(
                    user_id=self.user_id,
                )

                session.add(profile)

            profile.risk_profile = (
                clean_risk_profile
            )

            profile.investment_horizon_years = (
                int(investment_horizon_years)
                if investment_horizon_years
                is not None
                else None
            )

            profile.target_return = (
                float(target_return)
                if target_return is not None
                else None
            )

            profile.max_drawdown = (
                float(max_drawdown)
                if max_drawdown is not None
                else None
            )

            profile.monthly_investment = float(
                monthly_investment or 0
            )

            profile.preferred_markets = (
                clean_preferred_markets
            )

            profile.excluded_assets = (
                clean_excluded_assets
            )

            profile.ai_advice_enabled = bool(
                ai_advice_enabled
            )

            profile.ai_advice_style = (
                clean_ai_advice_style
            )

            profile.memo = str(
                memo or ""
            ).strip()

            profile.investment_preference_text = str(
                investment_preference_text
                or ""
            ).strip()

            profile.updated_at = datetime.now()

            session.flush()
            session.refresh(profile)

            return profile

    def delete_investment_profile(
        self,
    ) -> bool:
        """현재 사용자의 투자 성향을 삭제합니다."""
        if not self.user_id:
            return False

        with get_db_session() as session:
            profile = (
                session.query(InvestmentProfile)
                .filter(
                    InvestmentProfile.user_id
                    == self.user_id
                )
                .first()
            )

            if not profile:
                return False

            session.delete(profile)

            return True
    # -------------------------------------------------------------
    # 관심종목 (Watchlist) 관리
    # -------------------------------------------------------------

    def get_watchlist(
        self,
    ) -> List[Dict[str, Any]]:
        """현재 사용자의 관심종목 목록을 조회합니다."""
        if not self.user_id:
            return []

        with get_db_session() as session:
            rows = (
                session.query(
                    Watchlist,
                    AssetMaster,
                )
                .join(
                    AssetMaster,
                    AssetMaster.ticker
                    == Watchlist.ticker,
                )
                .filter(
                    Watchlist.user_id
                    == self.user_id
                )
                .order_by(
                    Watchlist.id.asc()
                )
                .all()
            )

            return [
                {
                    "id": watch.id,
                    "ticker": watch.ticker,
                    "name": asset.name,
                    "market": asset.market,
                    "exchange": asset.exchange,
                    "asset_type": asset.asset_type,
                    "currency": asset.currency,
                    "memo": watch.memo or "",
                }
                for watch, asset in rows
            ]

    def add_watchlist(
        self,
        ticker: str,
        memo: str = "",
    ) -> Watchlist:
        """현재 사용자의 관심종목을 추가합니다."""
        if not self.user_id:
            raise ValueError(
                "관심종목을 저장하려면 user_id가 필요합니다."
            )

        clean_ticker = str(
            ticker
        ).strip()

        if not clean_ticker:
            raise ValueError(
                "종목코드를 입력해야 합니다."
            )

        with get_db_session() as session:
            asset = (
                session.query(AssetMaster)
                .filter(
                    AssetMaster.ticker
                    == clean_ticker,
                    AssetMaster.is_active.is_(
                        True
                    ),
                )
                .first()
            )

            if not asset:
                raise ValueError(
                    "asset_master에 등록되지 않은 "
                    f"종목입니다: {clean_ticker}"
                )

            existing = (
                session.query(Watchlist)
                .filter(
                    Watchlist.user_id
                    == self.user_id,
                    Watchlist.ticker
                    == clean_ticker,
                )
                .first()
            )

            if existing:
                existing.memo = str(
                    memo or ""
                ).strip()

                return existing

            watch = Watchlist(
                user_id=self.user_id,
                ticker=clean_ticker,
                memo=str(
                    memo or ""
                ).strip(),
            )

            session.add(watch)
            session.flush()
            session.refresh(watch)

            return watch

    def update_watchlist_memo(
        self,
        ticker: str,
        memo: str = "",
    ) -> bool:
        """현재 사용자의 관심종목 메모를 수정합니다."""
        if not self.user_id:
            return False

        clean_ticker = str(
            ticker
        ).strip()

        if not clean_ticker:
            return False

        with get_db_session() as session:
            watch = (
                session.query(Watchlist)
                .filter(
                    Watchlist.user_id
                    == self.user_id,
                    Watchlist.ticker
                    == clean_ticker,
                )
                .first()
            )

            if not watch:
                return False

            watch.memo = str(
                memo or ""
            ).strip()

            return True

    def remove_watchlist(
        self,
        ticker: str,
    ) -> bool:
        """현재 사용자의 관심종목을 삭제합니다."""
        if not self.user_id:
            return False

        clean_ticker = str(
            ticker
        ).strip()

        if not clean_ticker:
            return False

        with get_db_session() as session:
            watch = (
                session.query(Watchlist)
                .filter(
                    Watchlist.user_id
                    == self.user_id,
                    Watchlist.ticker
                    == clean_ticker,
                )
                .first()
            )

            if not watch:
                return False

            session.delete(watch)

            return True

    # -------------------------------------------------------------
    # 사용자 설정 (UserSetting) 관리
    # -------------------------------------------------------------

    def get_user_settings(
        self,
    ) -> Optional[UserSetting]:
        """현재 사용자의 설정을 조회합니다."""
        if not self.user_id:
            return None

        with get_db_session() as session:
            return (
                session.query(UserSetting)
                .filter(
                    UserSetting.user_id
                    == self.user_id
                )
                .first()
            )

    def save_user_settings(
        self,
        morning_report_enabled: bool = True,
        morning_report_time: str = "07:30",
        kakao_enabled: bool = False,
        news_enabled: bool = True,
        ai_advice_enabled: bool = True,
    ) -> UserSetting:
        """
        현재 사용자의 설정을 저장합니다.

        기존 설정이 있으면 수정하고,
        없으면 새로 생성합니다.
        """
        if not self.user_id:
            raise ValueError(
                "사용자 설정을 저장하려면 user_id가 필요합니다."
            )

        clean_time = str(
            morning_report_time
        ).strip()

        try:
            report_time = datetime.strptime(
                clean_time,
                "%H:%M",
            ).time()
        except ValueError as exc:
            raise ValueError(
                "morning_report_time은 "
                "HH:MM 형식이어야 합니다."
            ) from exc

        with get_db_session() as session:
            settings = (
                session.query(UserSetting)
                .filter(
                    UserSetting.user_id
                    == self.user_id
                )
                .first()
            )

            if settings is None:
                settings = UserSetting(
                    user_id=self.user_id,
                    morning_report_time=report_time,
                )

                session.add(settings)

            settings.morning_report_enabled = bool(
                morning_report_enabled
            )

            settings.morning_report_time = (
                report_time
            )

            settings.kakao_enabled = bool(
                kakao_enabled
            )

            settings.news_enabled = bool(
                news_enabled
            )

            settings.ai_advice_enabled = bool(
                ai_advice_enabled
            )

            settings.updated_at = datetime.now()

            session.flush()
            session.refresh(settings)

            return settings

    def delete_user_settings(
        self,
    ) -> bool:
        """현재 사용자의 설정을 삭제합니다."""
        if not self.user_id:
            return False

        with get_db_session() as session:
            settings = (
                session.query(UserSetting)
                .filter(
                    UserSetting.user_id
                    == self.user_id
                )
                .first()
            )

            if not settings:
                return False

            session.delete(settings)

            return True
    
