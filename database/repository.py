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

from datetime import date, datetime, timedelta
import math
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID
from sqlalchemy.exc import IntegrityError

from core.config import ETFConfig, load_config
from database.connection import get_db_session, init_db
from database.models import (
    Account,
    AccountTarget,
    AssetMaster,
    CashFlow,
    Dividend,
    ExchangeRate,
    InvestmentProfile,
    KakaoCredential,
    MorningReport,
    Price,
    Profile,
    RecommendationLog,
    Transaction,
    UserSetting,
    Watchlist,
)

class Repository:
    def __init__(self, user_id: Optional[str] = None):
        init_db()
        try:
            self.user_id = UUID(user_id) if isinstance(user_id, str) else user_id
        except ValueError:
            # 일부 로컬 도구/테스트는 UUID가 아닌 식별자를 사용합니다.
            # Supabase에서 검증된 실제 user_id는 항상 UUID입니다.
            self.user_id = user_id

    def ensure_user_initialized(self) -> Dict[str, bool]:
        """새 사용자의 공용 기본 레코드를 멱등적으로 생성합니다."""
        if not self.user_id:
            raise ValueError(
                "사용자 초기화에는 user_id가 필요합니다."
            )

        created_profile = False
        created_settings = False

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
                session.add(
                    InvestmentProfile(
                        user_id=self.user_id,
                        risk_profile="balanced",
                        monthly_investment=0,
                        preferred_markets=[],
                        excluded_assets=[],
                        ai_advice_enabled=True,
                        ai_advice_style="balanced",
                        investment_preference_text="",
                    )
                )
                created_profile = True

            settings = (
                session.query(UserSetting)
                .filter(
                    UserSetting.user_id
                    == self.user_id
                )
                .first()
            )

            if settings is None:
                session.add(
                    UserSetting(
                        user_id=self.user_id,
                        morning_report_enabled=True,
                        morning_report_time=datetime.strptime(
                            "07:00",
                            "%H:%M",
                        ).time(),
                        kakao_enabled=False,
                        news_enabled=True,
                        ai_advice_enabled=True,
                    )
                )
                created_settings = True

            session.flush()

        return {
            "investment_profile_created":
                created_profile,
            "user_settings_created":
                created_settings,
        }

    @staticmethod
    def _parse_input_date(value, field_name: str) -> date:
        """API와 직접 호출 모두에서 동일한 날짜 형식을 검증합니다."""
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value

        try:
            return datetime.strptime(
                str(value).strip().replace("-", ""),
                "%Y%m%d",
            ).date()
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{field_name}은 YYYY-MM-DD 형식이어야 합니다."
            ) from exc

    def upsert_morning_report(self, report_date, html_content: str):
        """Create or replace this owner's report for a date."""
        if not self.user_id:
            raise ValueError("모닝 리포트 저장에는 user_id가 필요합니다.")
        parsed_date = self._parse_input_date(report_date, "report_date")
        with get_db_session() as session:
            report = session.query(MorningReport).filter(
                MorningReport.user_id == self.user_id,
                MorningReport.report_date == parsed_date,
            ).one_or_none()
            if report is None:
                report = MorningReport(
                    user_id=self.user_id,
                    report_date=parsed_date,
                    html_content=html_content,
                )
                session.add(report)
            else:
                report.html_content = html_content
                report.updated_at = datetime.now()
            session.flush()
            return report

    def mark_morning_report_kakao_sent(self, report_date):
        """Mark this owner's dated report as successfully delivered to Kakao."""
        if not self.user_id:
            raise ValueError("카카오 발송 완료 처리에는 user_id가 필요합니다.")
        parsed_date = self._parse_input_date(report_date, "report_date")
        with get_db_session() as session:
            report = session.query(MorningReport).filter(
                MorningReport.user_id == self.user_id,
                MorningReport.report_date == parsed_date,
            ).one_or_none()
            if report is None:
                return False
            report.kakao_sent_at = datetime.now()
            report.updated_at = datetime.now()
            session.flush()
            return True

    def get_morning_report_for_date(self, report_date):
        """Return this owner's report for one calendar date."""
        if not self.user_id:
            raise ValueError("모닝 리포트 조회에는 user_id가 필요합니다.")
        parsed_date = self._parse_input_date(report_date, "report_date")
        with get_db_session() as session:
            return session.query(MorningReport).filter(
                MorningReport.user_id == self.user_id,
                MorningReport.report_date == parsed_date,
            ).one_or_none()

    def get_latest_morning_report(self):
        """Return only the current owner's newest report."""
        if not self.user_id:
            raise ValueError("모닝 리포트 조회에는 user_id가 필요합니다.")
        with get_db_session() as session:
            return session.query(MorningReport).filter(
                MorningReport.user_id == self.user_id,
            ).order_by(
                MorningReport.report_date.desc(),
                MorningReport.updated_at.desc(),
            ).first()

    @staticmethod
    def _positive_number(value, field_name: str) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{field_name}은 숫자여야 합니다."
            ) from exc
        if not math.isfinite(number) or number <= 0:
            raise ValueError(
                f"{field_name}은 0보다 커야 합니다."
            )
        return number

    @staticmethod
    def _non_negative_number(value, field_name: str) -> float:
        try:
            number = float(value or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{field_name}은 숫자여야 합니다."
            ) from exc
        if not math.isfinite(number) or number < 0:
            raise ValueError(
                f"{field_name}은 0 이상이어야 합니다."
            )
        return number

    @staticmethod
    def _ensure_sell_quantity(
        transactions,
        *,
        ticker: str,
        transaction_type: str,
        quantity: float,
        transaction_date: date,
        exclude_transaction_id: Optional[int] = None,
        transaction_order: int = 10**30,
    ) -> None:
        """거래 반영 후 어느 시점에도 보유수량이 음수가 되지 않게 합니다."""
        ledger = [
            (
                row.transaction_date,
                int(row.id or 0),
                str(row.transaction_type).upper(),
                float(row.quantity or 0),
            )
            for row in transactions
            if (
                str(row.ticker).strip().upper() == ticker
                and row.id != exclude_transaction_id
            )
        ]
        ledger.append(
            (
                transaction_date,
                transaction_order,
                transaction_type,
                quantity,
            )
        )
        balance = 0.0
        for _, _, row_type, row_quantity in sorted(ledger):
            balance += row_quantity if row_type == "BUY" else -row_quantity
            if balance < -1e-9:
                raise ValueError(
                    "보유수량보다 많은 수량을 매도할 수 없습니다."
                )

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

    def save_exchange_rate(
        self,
        rate_date,
        from_currency: str,
        to_currency: str,
        rate: float,
    ) -> ExchangeRate:
        """
        환율을 저장하거나 갱신합니다.

        예:
            USD -> KRW
            rate = 1350.0

        같은 날짜/통화쌍이 이미 존재하면
        기존 값을 갱신합니다.
        """

        source = str(
            from_currency
        ).strip().upper()

        target = str(
            to_currency
        ).strip().upper()

        rate_value = float(
            rate or 0
        )

        if not source:
            raise ValueError(
                "기준 통화가 필요합니다."
            )

        if not target:
            raise ValueError(
                "대상 통화가 필요합니다."
            )

        if source == target:
            raise ValueError(
                "서로 다른 통화를 지정해야 합니다."
            )

        if rate_value <= 0:
            raise ValueError(
                "환율은 0보다 커야 합니다."
            )

        with get_db_session() as session:
            existing = (
                session.query(ExchangeRate)
                .filter(
                    ExchangeRate.rate_date
                    == rate_date,
                    ExchangeRate.from_currency
                    == source,
                    ExchangeRate.to_currency
                    == target,
                )
                .one_or_none()
            )

            if existing:
                existing.rate = rate_value

                session.flush()

                # 세션 종료 후에도 사용할 수 있도록
                # connection.py의 expire_on_commit=False를 사용합니다.
                return existing

            exchange_rate = ExchangeRate(
                rate_date=rate_date,
                from_currency=source,
                to_currency=target,
                rate=rate_value,
            )

            session.add(
                exchange_rate
            )

            session.flush()

            return exchange_rate

    def get_latest_exchange_rate(
        self,
        from_currency: str,
        to_currency: str,
    ) -> ExchangeRate | None:
        """
        지정한 통화쌍의 가장 최근 환율을 반환합니다.
        """

        source = str(
            from_currency
        ).strip().upper()

        target = str(
            to_currency
        ).strip().upper()

        if not source or not target:
            return None

        if source == target:
            return None

        with get_db_session() as session:
            return (
                session.query(ExchangeRate)
                .filter(
                    ExchangeRate.from_currency
                    == source,
                    ExchangeRate.to_currency
                    == target,
                    ExchangeRate.rate > 0,
                )
                .order_by(
                    ExchangeRate.rate_date.desc(),
                    ExchangeRate.id.desc(),
                )
                .first()
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

    def delete_account(
        self,
        account_id: int,
    ) -> bool:
        """
        현재 사용자의 계좌를 삭제합니다.
    
        transactions, cash_flows, dividends, account_targets는
        DB의 ON DELETE CASCADE에 의해 함께 삭제됩니다.
    
        삭제한 계좌가 기본 계좌였다면
        남아 있는 가장 오래된 계좌를
        새로운 기본 계좌로 지정합니다.
        """
    
        if not self.user_id:
            raise ValueError(
                "계좌를 삭제하려면 "
                "user_id가 필요합니다."
            )
    
        clean_account_id = int(
            account_id
        )
    
        with get_db_session() as session:
    
            account = (
                session.query(Account)
                .filter(
                    Account.id
                    == clean_account_id,
    
                    Account.user_id
                    == self.user_id,
                )
                .first()
            )
    
            if account is None:
                return False
    
    
            was_default = bool(
                account.is_default
            )
    
    
            # -----------------------------------------------------
            # 계좌 삭제
            #
            # DB Foreign Key의 ON DELETE CASCADE에 의해
            # transactions
            # cash_flows
            # dividends
            # account_targets
            # 도 함께 삭제됩니다.
            # -----------------------------------------------------
    
            session.delete(
                account
            )
    
            # 실제 DELETE를 DB에 먼저 반영해서
            # 이후 조회에서 삭제된 계좌가 제외되도록 합니다.
    
            session.flush()
    
    
            # -----------------------------------------------------
            # 삭제한 계좌가 기본 계좌였다면
            # 남은 계좌 중 가장 오래된 계좌를
            # 새로운 기본 계좌로 지정합니다.
            # -----------------------------------------------------
    
            if was_default:
    
                next_account = (
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
    
                if next_account is not None:
    
                    next_account.is_default = True
    
    
            return True

    # -------------------------------------------------------------
    # 현금 입출금 (CashFlow) 관리
    # -------------------------------------------------------------

    def get_cash_flows(
        self,
        account_id: int,
    ) -> List[CashFlow]:
        """
        현재 사용자가 소유한 계좌의
        현금 입출금 내역을 조회합니다.

        최신 내역부터 반환합니다.
        """

        if not self.user_id:
            return []

        clean_account_id = int(
            account_id
        )

        with get_db_session() as session:
            account = (
                session.query(Account)
                .filter(
                    Account.id
                    == clean_account_id,
                    Account.user_id
                    == self.user_id,
                )
                .first()
            )

            if account is None:
                return []

            return list(
                session.query(CashFlow)
                .filter(
                    CashFlow.account_id
                    == clean_account_id
                )
                .order_by(
                    CashFlow.flow_date.desc(),
                    CashFlow.id.desc(),
                )
                .all()
            )

    def create_cash_flow(
        self,
        account_id: int,
        flow_date,
        flow_type: str,
        amount: float,
        currency: str,
        memo: str = "",
        request_id: Optional[str] = None,
    ) -> CashFlow:
        """
        현재 사용자의 계좌에
        입금 또는 출금 내역을 등록합니다.

        flow_type:
        - DEPOSIT
        - WITHDRAWAL

        amount는 항상 양수로 저장합니다.
        """

        if not self.user_id:
            raise ValueError(
                "현금 입출금을 등록하려면 "
                "user_id가 필요합니다."
            )

        clean_account_id = int(
            account_id
        )

        clean_flow_type = (
            str(
                flow_type or ""
            )
            .strip()
            .upper()
        )

        if clean_flow_type not in (
            "DEPOSIT",
            "WITHDRAWAL",
        ):
            raise ValueError(
                "입출금 유형은 "
                "DEPOSIT 또는 WITHDRAWAL이어야 합니다."
            )

        clean_amount = self._positive_number(
            amount,
            "입출금 금액",
        )
        clean_flow_date = self._parse_input_date(
            flow_date,
            "입출금 날짜",
        )

        clean_currency = (
            str(
                currency or ""
            )
            .strip()
            .upper()
        )

        if clean_currency not in (
            "KRW",
            "USD",
        ):
            raise ValueError(
                "지원하지 않는 통화입니다."
            )

        try:
            with get_db_session() as session:
                account = (
                    session.query(Account)
                    .filter(
                        Account.id
                        == clean_account_id,
                        Account.user_id
                        == self.user_id,
                    )
                    .first()
                )

                if account is None:
                    raise ValueError(
                        "계좌를 찾을 수 없습니다."
                    )

                account_currency = str(
                    account.currency or "KRW"
                ).strip().upper()
                if clean_currency != account_currency:
                    raise ValueError(
                        "입출금 통화는 계좌 통화와 같아야 합니다."
                    )

                if request_id:
                    existing_request = session.query(CashFlow).filter(
                        CashFlow.request_id == request_id,
                        ).first()
                    if existing_request:
                        if existing_request.account_id != clean_account_id:
                            raise ValueError("이미 사용된 요청 ID입니다.")
                        if (existing_request.flow_date != clean_flow_date
                            or existing_request.flow_type != clean_flow_type
                            or float(existing_request.amount) != float(clean_amount)
                            or existing_request.currency != clean_currency
                            or existing_request.memo != str(memo or "").strip()):
                            raise ValueError("동일 요청 ID에 다른 저장 내용이 전달되었습니다.")
                        return existing_request

                cash_flow = CashFlow(
                    account_id=clean_account_id,
                    request_id=request_id,
                    flow_date=clean_flow_date,
                    flow_type=clean_flow_type,
                    amount=clean_amount,
                    currency=clean_currency,
                    memo=str(
                        memo or ""
                    ).strip(),
                )

                session.add(
                    cash_flow
                )

                session.flush()
                session.refresh(
                    cash_flow
                )

                return cash_flow

        except IntegrityError:
            if not request_id:
                raise
            with get_db_session() as retry_session:
                existing_request = retry_session.query(CashFlow).filter(
                    CashFlow.request_id == request_id,
                ).first()
                if existing_request is None:
                    raise
                if existing_request.account_id != clean_account_id:
                    raise ValueError("이미 사용된 요청 ID입니다.")
                if (existing_request.flow_date != clean_flow_date
                    or existing_request.flow_type != clean_flow_type
                    or float(existing_request.amount) != float(clean_amount)
                    or existing_request.currency != clean_currency
                    or existing_request.memo != str(memo or "").strip()):
                    raise ValueError("동일 요청 ID에 다른 저장 내용이 전달되었습니다.")
                return existing_request

    def update_cash_flow(
        self,
        cash_flow_id: int,
        flow_date,
        flow_type: str,
        amount: float,
        currency: str,
        memo: str = "",
    ) -> bool:
        """
        현재 사용자가 소유한 계좌의
        현금 입출금 내역을 수정합니다.
        """

        if not self.user_id:
            return False

        clean_cash_flow_id = int(
            cash_flow_id
        )

        clean_flow_type = (
            str(
                flow_type or ""
            )
            .strip()
            .upper()
        )

        if clean_flow_type not in (
            "DEPOSIT",
            "WITHDRAWAL",
        ):
            raise ValueError(
                "입출금 유형은 "
                "DEPOSIT 또는 WITHDRAWAL이어야 합니다."
            )

        clean_amount = self._positive_number(
            amount,
            "입출금 금액",
        )
        clean_flow_date = self._parse_input_date(
            flow_date,
            "입출금 날짜",
        )

        clean_currency = (
            str(
                currency or ""
            )
            .strip()
            .upper()
        )

        if clean_currency not in (
            "KRW",
            "USD",
        ):
            raise ValueError(
                "지원하지 않는 통화입니다."
            )

        with get_db_session() as session:
            cash_flow = (
                session.query(CashFlow)
                .join(
                    Account,
                    CashFlow.account_id
                    == Account.id,
                )
                .filter(
                    CashFlow.id
                    == clean_cash_flow_id,
                    Account.user_id
                    == self.user_id,
                )
                .first()
            )

            if cash_flow is None:
                return False

            account = (
                session.query(Account)
                .filter(
                    Account.id == cash_flow.account_id,
                    Account.user_id == self.user_id,
                )
                .first()
            )
            if account is None:
                return False

            account_currency = str(
                account.currency or "KRW"
            ).strip().upper()
            if clean_currency != account_currency:
                raise ValueError(
                    "입출금 통화는 계좌 통화와 같아야 합니다."
                )

            cash_flow.flow_date = (
                clean_flow_date
            )

            cash_flow.flow_type = (
                clean_flow_type
            )

            cash_flow.amount = (
                clean_amount
            )

            cash_flow.currency = (
                clean_currency
            )

            cash_flow.memo = str(
                memo or ""
            ).strip()

            cash_flow.updated_at = (
                datetime.now()
            )

            return True

    def delete_cash_flow(
        self,
        cash_flow_id: int,
    ) -> bool:
        """
        현재 사용자가 소유한 계좌의
        현금 입출금 내역을 삭제합니다.
        """

        if not self.user_id:
            return False

        clean_cash_flow_id = int(
            cash_flow_id
        )

        with get_db_session() as session:
            cash_flow = (
                session.query(CashFlow)
                .join(
                    Account,
                    CashFlow.account_id
                    == Account.id,
                )
                .filter(
                    CashFlow.id
                    == clean_cash_flow_id,
                    Account.user_id
                    == self.user_id,
                )
                .first()
            )

            if cash_flow is None:
                return False

            session.delete(
                cash_flow
            )

            return True
    
    
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

    # -------------------------------------------------------------
    # 계좌 목표 비중 (AccountTarget) 관리
    # -------------------------------------------------------------

    def get_account_targets(
        self,
        account_id: Optional[int] = None,
    ) -> List[ETFConfig]:
        """
        현재 사용자의 계좌별 목표 비중을 반환합니다.
    
        account_id가 지정되면 해당 계좌에 실제로
        저장된 목표 비중만 반환합니다.
    
        목표 비중이 등록되지 않은 계좌는
        빈 목록을 반환합니다.
    
        account_id가 None이면 현재 사용자의
        여러 계좌에 실제로 등록된 목표 비중만
        초기 자본금 비율로 통합합니다.
        """
    
        if not self.user_id:
            return []
    
        with get_db_session() as session:
    
            # -----------------------------------------------------
            # 특정 계좌의 목표 포트폴리오
            # -----------------------------------------------------
    
            if account_id is not None:
    
                account = (
                    session.query(Account)
                    .filter(
                        Account.id == account_id,
                        Account.user_id == self.user_id,
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
    
    
            # -----------------------------------------------------
            # 현재 사용자의 모든 계좌 조회
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
                return []
    
    
            # -----------------------------------------------------
            # 계좌가 하나뿐인 경우
            # -----------------------------------------------------
    
            if len(accounts) == 1:
    
                account = accounts[0]
    
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
    
    
            # -----------------------------------------------------
            # 여러 계좌의 목표 포트폴리오 수집
            #
            # 목표 포트폴리오가 없는 계좌는
            # 통합 대상에서 제외합니다.
            # -----------------------------------------------------
    
            account_targets = []
    
            for account in accounts:
    
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
    
                if not rows:
                    continue
    
                account_targets.append(
                    (
                        account,
                        rows,
                    )
                )
    
    
            # 모든 계좌에 목표 포트폴리오가 없다면
            # 빈 목록을 반환합니다.
    
            if not account_targets:
                return []
    
    
            # -----------------------------------------------------
            # 목표 포트폴리오가 있는 계좌들의
            # 초기 투자재원 합계
            # -----------------------------------------------------
    
            total_capital = sum(
                max(
                    0.0,
                    float(
                        account.initial_capital
                        or 0
                    ),
                )
                for account, _rows
                in account_targets
            )
    
    
            combined: Dict[
                str,
                Dict[str, Any],
            ] = {}
    
    
            # -----------------------------------------------------
            # 여러 계좌의 목표 비중 통합
            # -----------------------------------------------------
    
            for account, rows in account_targets:
    
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
    
                    # 초기 투자재원이 모두 0인 경우에는
                    # 목표가 있는 계좌끼리 동일 비중으로
                    # 통합합니다.
    
                    weight_factor = (
                        1.0
                        / len(account_targets)
                    )
    
    
                for target, asset in rows:
    
                    ticker = target.ticker
    
                    target_weight = float(
                        target.target_weight
                        or 0
                    )
    
                    dividend_yield = float(
                        target.dividend_yield
                        or 0
                    )
    
    
                    if ticker not in combined:
    
                        combined[ticker] = {
                            "ticker":
                                ticker,
    
                            "name":
                                asset.name,
    
                            "target_weight":
                                0.0,
    
                            "dividend_yield":
                                0.0,
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
    
    
            # -----------------------------------------------------
            # ETFConfig 형식으로 반환
            # -----------------------------------------------------
    
            return [
                ETFConfig(
                    ticker=info[
                        "ticker"
                    ],
    
                    name=info[
                        "name"
                    ],
    
                    target_weight=round(
                        info[
                            "target_weight"
                        ],
                        6,
                    ),
    
                    dividend_yield=round(
                        info[
                            "dividend_yield"
                        ],
                        6,
                    ),
                )
                for info
                in combined.values()
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
        request_id: Optional[str] = None,
        account_id: Optional[int] = None,
    ) -> Transaction:
        """현재 사용자의 거래 내역을 추가합니다."""
        if not self.user_id:
            raise ValueError(
                "거래를 저장하려면 user_id가 필요합니다."
            )

        clean_ticker = str(ticker or "").strip().upper()
        if not clean_ticker:
            raise ValueError("종목코드를 입력해야 합니다.")

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

        clean_quantity = self._positive_number(quantity, "거래 수량")
        clean_price = self._positive_number(price, "거래 가격")
        clean_fee = self._non_negative_number(fee, "수수료")
        clean_tax = self._non_negative_number(tax, "세금")
        tx_date = self._parse_input_date(transaction_date, "거래 날짜")

        try:
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

                if request_id:
                    existing_request = session.query(Transaction).filter(
                        Transaction.request_id == request_id,
                        ).first()
                    if existing_request:
                        if existing_request.account_id != account.id:
                            raise ValueError("이미 사용된 요청 ID입니다.")
                        if (existing_request.transaction_date != tx_date
                            or existing_request.ticker != clean_ticker
                            or existing_request.transaction_type != tx_type
                            or float(existing_request.quantity) != float(clean_quantity)
                            or float(existing_request.price) != float(clean_price)
                            or float(existing_request.fee) != float(clean_fee)
                            or float(existing_request.tax) != float(clean_tax)
                            or existing_request.memo != str(memo or "").strip()):
                            raise ValueError("동일 요청 ID에 다른 저장 내용이 전달되었습니다.")
                        return existing_request

                existing_transactions = (
                    session.query(Transaction)
                    .filter(Transaction.account_id == account.id)
                    .all()
                )
                self._ensure_sell_quantity(
                    existing_transactions,
                    ticker=clean_ticker,
                    transaction_type=tx_type,
                    quantity=clean_quantity,
                    transaction_date=tx_date,
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
                    request_id=request_id,
                    transaction_date=tx_date,
                    ticker=clean_ticker,
                    transaction_type=tx_type,
                    quantity=clean_quantity,
                    price=clean_price,
                    fee=clean_fee,
                    tax=clean_tax,
                    memo=str(
                        memo or ""
                    ).strip(),
                )

                session.add(transaction)
                session.flush()
                session.refresh(transaction)

                return transaction

        except IntegrityError:
            if not request_id:
                raise
            with get_db_session() as retry_session:
                existing_request = retry_session.query(Transaction).filter(
                    Transaction.request_id == request_id,
                ).first()
                if existing_request is None:
                    raise
                if existing_request.account_id != account.id:
                    raise ValueError("이미 사용된 요청 ID입니다.")
                if (existing_request.transaction_date != tx_date
                    or existing_request.ticker != clean_ticker
                    or existing_request.transaction_type != tx_type
                    or float(existing_request.quantity) != float(clean_quantity)
                    or float(existing_request.price) != float(clean_price)
                    or float(existing_request.fee) != float(clean_fee)
                    or float(existing_request.tax) != float(clean_tax)
                    or existing_request.memo != str(memo or "").strip()):
                    raise ValueError("동일 요청 ID에 다른 저장 내용이 전달되었습니다.")
                return existing_request

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

    def get_asset_chart_data(
        self,
        account_id: int,
        ticker: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        현재 사용자의 특정 계좌/종목에 대한
        가격 차트 데이터와 매수/매도 내역을 반환합니다.

        가격 데이터:
        - prices 테이블
        - 날짜 오름차순

        거래 데이터:
        - 현재 사용자가 소유한 지정 계좌만 조회
        - 지정 종목의 BUY / SELL 거래만 반환
        - 날짜 오름차순
        """

        if not self.user_id:
            return {
                "prices": [],
                "transactions": [],
            }


        clean_account_id = int(
            account_id
        )

        clean_ticker = (
            str(
                ticker or ""
            )
            .strip()
            .upper()
        )


        if not clean_ticker:
            return {
                "prices": [],
                "transactions": [],
            }


        with get_db_session() as session:

            # -----------------------------------------------------
            # 현재 사용자가 실제로 소유한 계좌인지 확인
            # -----------------------------------------------------

            account = (
                session.query(Account)
                .filter(
                    Account.id
                    == clean_account_id,

                    Account.user_id
                    == self.user_id,
                )
                .first()
            )


            if account is None:
                return {
                    "prices": [],
                    "transactions": [],
                }


            # -----------------------------------------------------
            # 가격 조회
            # -----------------------------------------------------

            price_query = (
                session.query(Price)
                .filter(
                    Price.ticker
                    == clean_ticker,

                    Price.close_price
                    > 0,
                )
            )


            if start_date:

                start_dt = (
                    datetime.strptime(
                        str(
                            start_date
                        )
                        .replace(
                            "-",
                            "",
                        ),
                        "%Y%m%d",
                    )
                    .date()
                )

                price_query = (
                    price_query.filter(
                        Price.price_date
                        >= start_dt
                    )
                )


            if end_date:

                end_dt = (
                    datetime.strptime(
                        str(
                            end_date
                        )
                        .replace(
                            "-",
                            "",
                        ),
                        "%Y%m%d",
                    )
                    .date()
                )

                price_query = (
                    price_query.filter(
                        Price.price_date
                        <= end_dt
                    )
                )


            if limit is not None:

                safe_limit = int(
                    limit
                )

                if safe_limit <= 0:
                    price_rows = []

                else:
                    price_rows = list(
                        price_query
                        .order_by(
                            Price.price_date.desc()
                        )
                        .limit(
                            safe_limit
                        )
                        .all()
                    )

                    price_rows.reverse()

            else:
                price_rows = list(
                    price_query
                    .order_by(
                        Price.price_date.asc()
                    )
                    .all()
                )


            # -----------------------------------------------------
            # 해당 계좌의 실제 매수/매도 내역 조회
            # -----------------------------------------------------

            transaction_query = (
                session.query(Transaction)
                .filter(
                    Transaction.account_id
                    == clean_account_id,

                    Transaction.ticker
                    == clean_ticker,
                )
            )


            if start_date:
                transaction_query = (
                    transaction_query.filter(
                        Transaction.transaction_date
                        >= start_dt
                    )
                )


            if end_date:
                transaction_query = (
                    transaction_query.filter(
                        Transaction.transaction_date
                        <= end_dt
                    )
                )


            transaction_rows = list(
                transaction_query
                .order_by(
                    Transaction.transaction_date.asc(),
                    Transaction.id.asc(),
                )
                .all()
            )


            # -----------------------------------------------------
            # 자산 정보
            # -----------------------------------------------------

            asset = (
                session.query(AssetMaster)
                .filter(
                    AssetMaster.ticker
                    == clean_ticker
                )
                .first()
            )


            # -----------------------------------------------------
            # API에서 바로 사용할 수 있는 형태로 변환
            # -----------------------------------------------------

            prices = [
                {
                    "date":
                        row.price_date.isoformat(),

                    "open":
                        float(
                            row.open_price
                            or 0
                        ),

                    "high":
                        float(
                            row.high_price
                            or 0
                        ),

                    "low":
                        float(
                            row.low_price
                            or 0
                        ),

                    "close":
                        float(
                            row.close_price
                            or 0
                        ),

                    "volume":
                        int(
                            row.volume
                            or 0
                        ),
                }
                for row in price_rows
            ]


            transactions = [
                {
                    "id":
                        row.id,

                    "date":
                        row.transaction_date.isoformat(),

                    "type":
                        row.transaction_type,

                    "quantity":
                        float(
                            row.quantity
                            or 0
                        ),

                    "price":
                        float(
                            row.price
                            or 0
                        ),

                    "fee":
                        float(
                            row.fee
                            or 0
                        ),

                    "tax":
                        float(
                            row.tax
                            or 0
                        ),

                    "memo":
                        row.memo
                        or "",
                }
                for row in transaction_rows
            ]


            return {
                "ticker":
                    clean_ticker,

                "name":
                    (
                        asset.name
                        if asset
                        else clean_ticker
                    ),

                "currency":
                    (
                        asset.currency
                        if asset
                        else account.currency
                    ),

                "market":
                    (
                        asset.market
                        if asset
                        else ""
                    ),

                "prices":
                    prices,

                "transactions":
                    transactions,
            }
            
    
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

        clean_ticker = str(ticker or "").strip().upper()
        if not clean_ticker:
            raise ValueError("종목코드를 입력해야 합니다.")

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

        clean_quantity = self._positive_number(quantity, "거래 수량")
        clean_price = self._positive_number(price, "거래 가격")
        clean_fee = self._non_negative_number(fee, "수수료")
        clean_tax = self._non_negative_number(tax, "세금")
        tx_date = self._parse_input_date(transaction_date, "거래 날짜")

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

            existing_transactions = (
                session.query(Transaction)
                .filter(
                    Transaction.account_id
                    == transaction.account_id
                )
                .all()
            )
            self._ensure_sell_quantity(
                existing_transactions,
                ticker=clean_ticker,
                transaction_type=tx_type,
                quantity=clean_quantity,
                transaction_date=tx_date,
                exclude_transaction_id=tx_id,
                transaction_order=tx_id,
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

            transaction.fee = clean_fee
            transaction.tax = clean_tax

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

    def get_kakao_credential(self) -> Optional[KakaoCredential]:
        if not self.user_id:
            return None
        with get_db_session() as session:
            return session.query(KakaoCredential).filter(
                KakaoCredential.user_id == self.user_id
            ).first()

    def save_kakao_credential(
        self,
        access_token_encrypted: str,
        refresh_token_encrypted: str,
        access_token_expires_at=None,
        refresh_token_expires_at=None,
        scopes: str = "",
    ) -> KakaoCredential:
        if not self.user_id:
            raise ValueError("Kakao credential requires user_id")
        with get_db_session() as session:
            row = session.query(KakaoCredential).filter(
                KakaoCredential.user_id == self.user_id
            ).first()
            if row is None:
                row = KakaoCredential(user_id=self.user_id)
                session.add(row)
            row.access_token_encrypted = access_token_encrypted
            row.refresh_token_encrypted = refresh_token_encrypted
            row.access_token_expires_at = access_token_expires_at
            row.refresh_token_expires_at = refresh_token_expires_at
            row.scopes = scopes
            row.updated_at = datetime.now()
            session.flush()
            session.refresh(row)
            return row

    def delete_kakao_credential(self) -> bool:
        if not self.user_id:
            return False
        with get_db_session() as session:
            row = session.query(KakaoCredential).filter(
                KakaoCredential.user_id == self.user_id
            ).first()
            if row is None:
                return False
            session.delete(row)
            return True

    def is_active_member(self) -> bool:
        """Return True only while this repository owner has active membership."""
        if not self.user_id:
            return False
        with get_db_session() as session:
            profile = session.query(Profile).filter(Profile.id == self.user_id).one_or_none()
            return bool(profile is not None and profile.is_active)

    @staticmethod
    def get_morning_report_user_ids() -> List[UUID]:
        """Return users who opted in to scheduled morning reports."""
        with get_db_session() as session:
            return [
                row[0]
                for row in (
                    session.query(UserSetting.user_id)
                    .join(Profile, Profile.id == UserSetting.user_id)
                    .filter(
                        UserSetting.morning_report_enabled.is_(True),
                        Profile.is_active.is_(True),
                    )
                    .order_by(UserSetting.user_id.asc())
                    .all()
                )
            ]

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
    
