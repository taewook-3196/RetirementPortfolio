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
from typing import List, Optional, Tuple, Dict, Any
from core.config import ETFConfig, load_config
from database.connection import get_db_session, init_db
from database.models import (
    Price,
    Transaction,
    Dividend,
    RecommendationLog,
    AssetMaster,
    Account,
    AccountTarget,
)


class Repository:
    def __init__(self, user_id: Optional[str] = None):
        init_db()
        self.user_id = user_id    
    # -------------------------------------------------------------
    # 가격 데이터 (Price) 관리
    # -------------------------------------------------------------
    def upsert_prices(self, price_dicts: List[Dict[str, Any]]) -> int:
        """
        가격 목록을 삽입하거나 중복 시 갱신(upsert)합니다.
        성공적으로 반영된 행 개수를 반환합니다.
        """
        if not price_dicts:
            return 0

        inserted_count = 0
        with get_db_session() as session:
            for item in price_dicts:
                date_str = str(item.get("date", "")).replace("-", "")
                ticker = str(item.get("ticker", "")).strip()
                if not date_str or not ticker:
                    continue

                price_date = datetime.strptime(date_str, "%Y%m%d").date()
                
                existing = (
                    session.query(Price)
                    .filter(Price.price_date == price_date, Price.ticker == ticker)
                    .first()
                )
                if existing:                    
                    existing.open_price = float(item.get("open_price", existing.open_price))
                    existing.high_price = float(item.get("high_price", existing.high_price))
                    existing.low_price = float(item.get("low_price", existing.low_price))
                    existing.close_price = float(item.get("close_price", existing.close_price))
                    existing.nav = float(item.get("nav", existing.nav or 0.0))
                    existing.volume = int(item.get("volume", existing.volume))
                    existing.trading_value = float(item.get("trading_value", existing.trading_value))
                else:
                    new_p = Price(
                        price_date=price_date,
                        ticker=ticker,                        
                        open_price=float(item.get("open_price", 0.0)),
                        high_price=float(item.get("high_price", 0.0)),
                        low_price=float(item.get("low_price", 0.0)),
                        close_price=float(item.get("close_price", 0.0)),
                        nav=float(item.get("nav", 0.0)),
                        volume=int(item.get("volume", 0)),
                        trading_value=float(item.get("trading_value", 0.0)),
                    )
                    session.add(new_p)
                inserted_count += 1
        return inserted_count

    def get_prices(
        self,
        ticker: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Price]:
        """특정 종목의 가격 이력을 날짜 오름차순으로 조회합니다 (0원 미거래일 제외)."""
        with get_db_session() as session:
            query = session.query(Price).filter(Price.ticker == ticker, Price.close_price > 0)
            if start_date:
                start_dt = datetime.strptime(start_date.replace("-", ""), "%Y%m%d").date()
                query = query.filter(Price.price_date >= start_dt)
            
            if end_date:
                end_dt = datetime.strptime(end_date.replace("-", ""), "%Y%m%d").date()
                query = query.filter(Price.price_date <= end_dt)
    
            query = query.order_by(Price.price_date.asc())
            if limit:
                # 최신 기준 limit개 조회 후 오름차순 정렬
                recent_query = (
                    session.query(Price)
                    .filter(Price.ticker == ticker, Price.close_price > 0)
                    .order_by(Price.price_date.desc())
                    .limit(limit)
                )
                prices = list(recent_query)
                prices.reverse()
                return prices
            return list(query.all())

    def get_latest_price(self, ticker: str) -> Optional[Price]:
        """특정 종목의 가장 최신 가격 데이터를 조회합니다 (0원 미거래일 제외)."""
        with get_db_session() as session:
            return (
                session.query(Price)
                .filter(Price.ticker == ticker, Price.close_price > 0)
                .order_by(Price.price_date.desc())
                .first()
            )

    def get_recent_3m_high(
        self, ticker: str, as_of_date: Optional[str] = None, exclude_today: bool = False
    ) -> Tuple[float, str]:
        """
        기준일(기본: 최신 가격일 또는 오늘) 기준 최근 3개월 최고 종가와 그 발생일을 반환합니다.
        exclude_today가 True일 경우 당일 가격을 제외한 직전 3개월 고점을 반환하여 고점 돌파/상승률을 측정합니다.
        반환: (최고 종가, 발생일자)
        """
        with get_db_session() as session:
            latest = self.get_latest_price(ticker)
            if not latest:
                return (0.0, "")

            if as_of_date:
                ref_date = datetime.strptime(as_of_date.replace("-", ""), "%Y%m%d").date()
            else:
                ref_date = latest.price_date
            start_date = ref_date - timedelta(days=93)  # 약 3개월

            query = session.query(Price).filter(
                Price.ticker == ticker,
                Price.close_price > 0,
                Price.price_date >= start_date,
            )

            if exclude_today:
                query = query.filter(Price.price_date < ref_date)
            else:
                query = query.filter(Price.price_date <= ref_date)

            high_row = query.order_by(
                Price.close_price.desc(),
                Price.price_date.desc(),
            ).first()

            if high_row:
                return (
                    float(high_row.close_price),
                    high_row.price_date.strftime("%Y%m%d"),
                )

            return (
                float(latest.close_price),
                latest.price_date.strftime("%Y%m%d"),
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
                .filter(Account.user_id == self.user_id)
                .order_by(Account.is_default.desc(), Account.id.asc())
                .all()
            )

    def get_account(self, account_id: int) -> Optional[Account]:
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

    def get_default_account(self) -> Optional[Account]:
        """현재 사용자의 기본 계좌를 조회합니다."""
        if not self.user_id:
            return None

        with get_db_session() as session:
            acc = (
                session.query(Account)
                .filter(
                    Account.user_id == self.user_id,
                    Account.is_default.is_(True),
                )
                .first()
            )

            if not acc:
                acc = (
                    session.query(Account)
                    .filter(Account.user_id == self.user_id)
                    .order_by(Account.id.asc())
                    .first()
                )

            return acc
            
    def create_account(
        self,
        account_name: str,
        account_number: str = "",
        broker: str = "",
        initial_capital: float = 100000000.0,
        base_monthly: float = 10000000.0,
        max_additional_monthly: float = 3000000.0,
        buy_cycle_type: str = "monthly",
        buy_cycle_detail: str = "25",
        is_default: int = 0,
        memo: str = "",
    ) -> Account:
        """현재 사용자의 신규 계좌를 생성합니다."""
        if not self.user_id:
            raise ValueError("계좌를 생성하려면 user_id가 필요합니다.")

        with get_db_session() as session:
            if is_default:
                (
                    session.query(Account)
                    .filter(Account.user_id == self.user_id)
                    .update({Account.is_default: False})
                )

            acc = Account(
                user_id=self.user_id,
                account_name=account_name.strip(),
                account_number=account_number.strip(),
                broker=broker.strip(),
                initial_capital=float(initial_capital),
                base_monthly=float(base_monthly),
                max_additional_monthly=float(max_additional_monthly),
                buy_cycle_type=buy_cycle_type.strip() if buy_cycle_type else "monthly",
                buy_cycle_detail=buy_cycle_detail.strip() if buy_cycle_detail else "25",
                is_default=bool(is_default),
                memo=memo.strip(),
            )

            session.add(acc)
            session.flush()
            session.refresh(acc)

            # 신규 계좌 초기 목표 비중 시딩
            cfg = load_config()

            for etf in cfg.etfs:
                asset = (
                    session.query(AssetMaster)
                    .filter(AssetMaster.ticker == etf.ticker)
                    .first()
                )

                if not asset:
                    session.add(
                        AssetMaster(
                            ticker=etf.ticker,
                            name=etf.name,
                            market="KR",
                            exchange="KRX",
                            asset_type="ETF",
                            currency="KRW",
                            is_active=True,
                        )
                    )
                    session.flush()

                session.add(
                    AccountTarget(
                        account_id=acc.id,
                        ticker=etf.ticker,
                        target_weight=etf.target_weight,
                        dividend_yield=etf.dividend_yield,
                    )
                )

            return acc
    def update_account(
        self,
        account_id: int,
        account_name: str,
        account_number: str = "",
        broker: str = "",
        initial_capital: float = 100000000.0,
        base_monthly: float = 10000000.0,
        max_additional_monthly: float = 3000000.0,
        buy_cycle_type: str = "monthly",
        buy_cycle_detail: str = "25",
        is_default: int = 0,
        memo: str = "",
    ) -> bool:
        """현재 사용자의 계좌 정보를 수정합니다."""
        if not self.user_id:
            return False

        with get_db_session() as session:
            acc = (
                session.query(Account)
                .filter(
                    Account.id == account_id,
                    Account.user_id == self.user_id,
                )
                .first()
            )

            if not acc:
                return False

            if is_default:
                (
                    session.query(Account)
                    .filter(
                        Account.user_id == self.user_id,
                        Account.id != account_id,
                    )
                    .update({Account.is_default: False})
                )

            acc.account_name = account_name.strip()
            acc.account_number = account_number.strip()
            acc.broker = broker.strip()
            acc.initial_capital = float(initial_capital)
            acc.base_monthly = float(base_monthly)
            acc.max_additional_monthly = float(max_additional_monthly)
            acc.buy_cycle_type = buy_cycle_type.strip() if buy_cycle_type else "monthly"
            acc.buy_cycle_detail = buy_cycle_detail.strip() if buy_cycle_detail else "25"
            acc.is_default = bool(is_default)
            acc.memo = memo.strip()
            acc.updated_at = datetime.now()

            return True
            
    def set_default_account(self, account_id: int) -> bool:
        """현재 사용자의 계좌를 기본 계좌로 지정합니다."""
        if not self.user_id:
            return False

        with get_db_session() as session:
            acc = (
                session.query(Account)
                .filter(
                    Account.id == account_id,
                    Account.user_id == self.user_id,
                )
                .first()
            )

            if not acc:
                return False

            (
                session.query(Account)
                .filter(Account.user_id == self.user_id)
                .update({Account.is_default: False})
            )

            acc.is_default = True
            return True
            
    def delete_account(self, account_id: int) -> bool:
        """현재 사용자의 계좌를 삭제합니다."""
        if not self.user_id:
            return False

        with get_db_session() as session:
            acc = (
                session.query(Account)
                .filter(
                    Account.id == account_id,
                    Account.user_id == self.user_id,
                )
                .first()
            )

            if not acc:
                return False

            was_default = bool(acc.is_default)

            session.delete(acc)
            session.flush()

            # 삭제한 계좌가 기본 계좌였다면,
            # 현재 사용자의 남은 첫 번째 계좌를 기본 계좌로 지정
            if was_default:
                remaining = (
                    session.query(Account)
                    .filter(Account.user_id == self.user_id)
                    .order_by(Account.id.asc())
                    .first()
                )

                if remaining:
                    remaining.is_default = True

            return True
            
    def get_account_targets(self, account_id: Optional[int] = None) -> List[ETFConfig]:
        """
        현재 사용자의 계좌별 목표 비중을 반환합니다.

        account_id가 지정되면 해당 계좌의 목표 비중을 반환하고,
        None이면 현재 사용자의 모든 계좌 목표 비중을 자본금 비율로 통합합니다.
        """
        if not self.user_id:
            return []

        with get_db_session() as session:
            # 특정 계좌 조회
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
                    session.query(AccountTarget, AssetMaster)
                    .join(
                        AssetMaster,
                        AssetMaster.ticker == AccountTarget.ticker,
                    )
                    .filter(AccountTarget.account_id == account_id)
                    .order_by(AccountTarget.id.asc())
                    .all()
                )

                if rows:
                    return [
                        ETFConfig(
                            ticker=target.ticker,
                            name=asset.name,
                            target_weight=float(target.target_weight),
                            dividend_yield=float(target.dividend_yield or 0.0),
                        )
                        for target, asset in rows
                    ]

                return list(load_config().etfs)

            # 현재 사용자의 모든 계좌
            accounts = (
                session.query(Account)
                .filter(Account.user_id == self.user_id)
                .order_by(Account.id.asc())
                .all()
            )

            if not accounts:
                return list(load_config().etfs)

            # 계좌가 하나뿐인 경우
            if len(accounts) == 1:
                rows = (
                    session.query(AccountTarget, AssetMaster)
                    .join(
                        AssetMaster,
                        AssetMaster.ticker == AccountTarget.ticker,
                    )
                    .filter(AccountTarget.account_id == accounts[0].id)
                    .order_by(AccountTarget.id.asc())
                    .all()
                )

                if rows:
                    return [
                        ETFConfig(
                            ticker=target.ticker,
                            name=asset.name,
                            target_weight=float(target.target_weight),
                            dividend_yield=float(target.dividend_yield or 0.0),
                        )
                        for target, asset in rows
                    ]

                return list(load_config().etfs)

            # 여러 계좌: initial_capital 비율로 목표 비중 통합
            total_cap = sum(
                max(0.0, float(account.initial_capital or 0.0))
                for account in accounts
            )

            combined: Dict[str, Dict[str, Any]] = {}

            for account in accounts:
                capital = max(0.0, float(account.initial_capital or 0.0))

                if total_cap > 0:
                    weight_factor = capital / total_cap
                else:
                    weight_factor = 1.0 / len(accounts)

                rows = (
                    session.query(AccountTarget, AssetMaster)
                    .join(
                        AssetMaster,
                        AssetMaster.ticker == AccountTarget.ticker,
                    )
                    .filter(AccountTarget.account_id == account.id)
                    .order_by(AccountTarget.id.asc())
                    .all()
                )

                if rows:
                    targets = [
                        (
                            target.ticker,
                            asset.name,
                            float(target.target_weight),
                            float(target.dividend_yield or 0.0),
                        )
                        for target, asset in rows
                    ]
                else:
                    targets = [
                        (
                            etf.ticker,
                            etf.name,
                            float(etf.target_weight),
                            float(etf.dividend_yield or 0.0),
                        )
                        for etf in load_config().etfs
                    ]

                for ticker, name, target_weight, dividend_yield in targets:
                    if ticker not in combined:
                        combined[ticker] = {
                            "ticker": ticker,
                            "name": name,
                            "target_weight": 0.0,
                            "dividend_yield": 0.0,
                        }

                    combined[ticker]["target_weight"] += (
                        target_weight * weight_factor
                    )
                    combined[ticker]["dividend_yield"] += (
                        dividend_yield * weight_factor
                    )

            return [
                ETFConfig(
                    ticker=info["ticker"],
                    name=info["name"],
                    target_weight=round(info["target_weight"], 4),
                    dividend_yield=round(info["dividend_yield"], 4),
                )
                for info in combined.values()
            ]
            
    def save_account_targets(self, account_id: int, targets: List[ETFConfig]) -> None:
        """현재 사용자의 계좌 목표 비중 목록을 저장합니다."""
        if not self.user_id:
            raise ValueError("목표 비중을 저장하려면 user_id가 필요합니다.")

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
                raise ValueError("현재 사용자의 계좌를 찾을 수 없습니다.")

            # 필요한 종목이 asset_master에 없으면 먼저 등록
            for target in targets:
                asset = (
                    session.query(AssetMaster)
                    .filter(AssetMaster.ticker == target.ticker)
                    .first()
                )

                if not asset:
                    session.add(
                        AssetMaster(
                            ticker=target.ticker,
                            name=target.name,
                            market="KR",
                            exchange="KRX",
                            asset_type="ETF",
                            currency="KRW",
                            is_active=True,
                        )
                    )

            session.flush()

            # 기존 목표 비중 삭제
            (
                session.query(AccountTarget)
                .filter(AccountTarget.account_id == account_id)
                .delete()
            )

            # 새 목표 비중 저장
            for target in targets:
                session.add(
                    AccountTarget(
                        account_id=account_id,
                        ticker=target.ticker,
                        target_weight=float(target.target_weight),
                        dividend_yield=float(target.dividend_yield or 0.0),
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
        quantity: int,
        price: float,
        fee: float = 0.0,
        tax: float = 0.0,
        memo: str = "",
        account_id: Optional[int] = None,
    ) -> Transaction:
        """현재 사용자의 거래 내역을 추가합니다."""
        if not self.user_id:
            raise ValueError("거래를 저장하려면 user_id가 필요합니다.")

        tx_type = transaction_type.upper().strip()
        if tx_type not in ("BUY", "SELL"):
            raise ValueError("거래 유형은 BUY 또는 SELL이어야 합니다.")

        tx_date = datetime.strptime(
            transaction_date.replace("-", ""),
            "%Y%m%d",
        ).date()

        with get_db_session() as session:
            # 계좌가 지정되지 않으면 현재 사용자의 기본 계좌 사용
            if account_id is None:
                account = (
                    session.query(Account)
                    .filter(
                        Account.user_id == self.user_id,
                        Account.is_default.is_(True),
                    )
                    .first()
                )

                if not account:
                    account = (
                        session.query(Account)
                        .filter(Account.user_id == self.user_id)
                        .order_by(Account.id.asc())
                        .first()
                    )
            else:
                account = (
                    session.query(Account)
                    .filter(
                        Account.id == account_id,
                        Account.user_id == self.user_id,
                    )
                    .first()
                )

            if not account:
                raise ValueError("거래를 저장할 계좌를 찾을 수 없습니다.")

            # asset_master에 종목이 존재해야 함
            asset = (
                session.query(AssetMaster)
                .filter(AssetMaster.ticker == ticker)
                .first()
            )

            if not asset:
                raise ValueError(
                    f"asset_master에 등록되지 않은 종목입니다: {ticker}"
                )

            tx = Transaction(
                account_id=account.id,
                transaction_date=tx_date,
                ticker=ticker,
                transaction_type=tx_type,
                quantity=quantity,
                price=float(price),
                fee=float(fee),
                tax=float(tax),
                memo=memo.strip(),
            )

            session.add(tx)
            session.flush()
            session.refresh(tx)

            return tx

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
                .join(Account, Transaction.account_id == Account.id)
                .filter(Account.user_id == self.user_id)
            )

            if ticker:
                query = query.filter(Transaction.ticker == ticker)

            if account_id is not None:
                query = query.filter(Transaction.account_id == account_id)

            return list(
                query.order_by(
                    Transaction.transaction_date.asc(),
                    Transaction.id.asc(),
                ).all()
            )

    def update_transaction(
        self,
        tx_id: int,
        transaction_date: str,
        ticker: str,
        transaction_type: str,
        quantity: int,
        price: float,
        fee: float = 0.0,
        tax: float = 0.0,
        memo: str = "",
        account_id: Optional[int] = None,
    ) -> bool:
        """현재 사용자의 거래 내역을 수정합니다."""
        if not self.user_id:
            return False

        tx_type = transaction_type.upper().strip()
        if tx_type not in ("BUY", "SELL"):
            raise ValueError("거래 유형은 BUY 또는 SELL이어야 합니다.")

        tx_date = datetime.strptime(
            transaction_date.replace("-", ""),
            "%Y%m%d",
        ).date()

        with get_db_session() as session:
            tx = (
                session.query(Transaction)
                .join(Account, Transaction.account_id == Account.id)
                .filter(
                    Transaction.id == tx_id,
                    Account.user_id == self.user_id,
                )
                .first()
            )

            if not tx:
                return False

            asset = (
                session.query(AssetMaster)
                .filter(AssetMaster.ticker == ticker)
                .first()
            )

            if not asset:
                raise ValueError(
                    f"asset_master에 등록되지 않은 종목입니다: {ticker}"
                )

            if account_id is not None:
                new_account = (
                    session.query(Account)
                    .filter(
                        Account.id == account_id,
                        Account.user_id == self.user_id,
                    )
                    .first()
                )

                if not new_account:
                    raise ValueError("변경할 계좌를 찾을 수 없습니다.")

                tx.account_id = new_account.id

            tx.transaction_date = tx_date
            tx.ticker = ticker
            tx.transaction_type = tx_type
            tx.quantity = quantity
            tx.price = float(price)
            tx.fee = float(fee)
            tx.tax = float(tax)
            tx.memo = memo.strip()
            tx.updated_at = datetime.now()

            return True

    def delete_transaction(self, tx_id: int) -> bool:
        """현재 사용자의 거래 내역을 삭제합니다."""
        if not self.user_id:
            return False

        with get_db_session() as session:
            tx = (
                session.query(Transaction)
                .join(Account, Transaction.account_id == Account.id)
                .filter(
                    Transaction.id == tx_id,
                    Account.user_id == self.user_id,
                )
                .first()
            )

            if not tx:
                return False

            session.delete(tx)
            return True
            
    # -------------------------------------------------------------
    # 분배금 (Dividend) 관리
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
        """현재 사용자의 분배금 내역을 추가합니다."""
        if not self.user_id:
            raise ValueError("분배금을 저장하려면 user_id가 필요합니다.")

        div_date = datetime.strptime(
            dividend_date.replace("-", ""),
            "%Y%m%d",
        ).date()

        net = (
            float(net_amount)
            if net_amount is not None
            else float(gross_amount) - float(tax)
        )

        with get_db_session() as session:
            # 계좌가 지정되지 않으면 현재 사용자의 기본 계좌 사용
            if account_id is None:
                account = (
                    session.query(Account)
                    .filter(
                        Account.user_id == self.user_id,
                        Account.is_default.is_(True),
                    )
                    .first()
                )

                if not account:
                    account = (
                        session.query(Account)
                        .filter(Account.user_id == self.user_id)
                        .order_by(Account.id.asc())
                        .first()
                    )
            else:
                account = (
                    session.query(Account)
                    .filter(
                        Account.id == account_id,
                        Account.user_id == self.user_id,
                    )
                    .first()
                )

            if not account:
                raise ValueError("분배금을 저장할 계좌를 찾을 수 없습니다.")

            asset = (
                session.query(AssetMaster)
                .filter(AssetMaster.ticker == ticker)
                .first()
            )

            if not asset:
                raise ValueError(
                    f"asset_master에 등록되지 않은 종목입니다: {ticker}"
                )

            div = Dividend(
                account_id=account.id,
                dividend_date=div_date,
                ticker=ticker,
                currency=asset.currency,
                gross_amount=float(gross_amount),
                tax=float(tax),
                net_amount=net,
            )

            session.add(div)
            session.flush()
            session.refresh(div)

            return div

    def get_dividends(
        self,
        ticker: Optional[str] = None,
        account_id: Optional[int] = None,
    ) -> List[Dividend]:
        """현재 사용자의 분배금 수령 내역을 조회합니다."""
        if not self.user_id:
            return []

        with get_db_session() as session:
            query = (
                session.query(Dividend)
                .join(Account, Dividend.account_id == Account.id)
                .filter(Account.user_id == self.user_id)
            )

            if ticker:
                query = query.filter(Dividend.ticker == ticker)

            if account_id is not None:
                query = query.filter(Dividend.account_id == account_id)

            return list(
                query.order_by(
                    Dividend.dividend_date.asc(),
                    Dividend.id.asc(),
                ).all()
            )
            
    # -------------------------------------------------------------
    # 매수 추천 기록 (RecommendationLog) 관리
    # -------------------------------------------------------------
    def save_recommendations(self, rec_list: List[Dict[str, Any]]) -> None:
        """현재 사용자의 매수 추천 결과를 저장합니다."""
        if not self.user_id:
            raise ValueError("추천 결과를 저장하려면 user_id가 필요합니다.")

        with get_db_session() as session:
            for item in rec_list:
                date_value = item.get(
                    "date",
                    datetime.now().strftime("%Y-%m-%d"),
                )

                if isinstance(date_value, datetime):
                    recommendation_date = date_value.date()
                elif hasattr(date_value, "year") and hasattr(date_value, "month"):
                    recommendation_date = date_value
                else:
                    recommendation_date = datetime.strptime(
                        str(date_value).replace("-", ""),
                        "%Y%m%d",
                    ).date()

                log = RecommendationLog(
                    user_id=self.user_id,
                    recommendation_date=recommendation_date,
                    ticker=item.get("ticker", ""),
                    name=item.get("name", ""),
                    target_weight=float(item.get("target_weight", 0.0)),
                    current_weight=float(item.get("current_weight", 0.0)),
                    weight_gap=float(item.get("weight_gap", 0.0)),
                    recent_high=float(item.get("recent_high", 0.0)),
                    current_price=float(item.get("current_price", 0.0)),
                    drawdown=float(item.get("drawdown", 0.0)),
                    drawdown_score=int(item.get("drawdown_score", 0)),
                    priority_score=float(item.get("priority_score", 0.0)),
                    recommended_buy=int(item.get("recommended_buy", 0)),
                    expected_weight_after=float(
                        item.get("expected_weight_after", 0.0)
                    ),
                    reason=item.get("reason", ""),
                )

                session.add(log)

    def get_latest_recommendations(self) -> List[RecommendationLog]:
        """현재 사용자의 가장 최근 매수 추천 결과를 조회합니다."""
        if not self.user_id:
            return []

        with get_db_session() as session:
            latest_date_row = (
                session.query(RecommendationLog.recommendation_date)
                .filter(RecommendationLog.user_id == self.user_id)
                .order_by(RecommendationLog.recommendation_date.desc())
                .first()
            )

            if not latest_date_row:
                return []

            latest_date = latest_date_row[0]

            return list(
                session.query(RecommendationLog)
                .filter(
                    RecommendationLog.user_id == self.user_id,
                    RecommendationLog.recommendation_date == latest_date,
                )
                .order_by(RecommendationLog.id.asc())
                .all()
            )
    
    # -------------------------------------------------------------
    # 자산 마스터 (AssetMaster) 관리 및 검색
    # -------------------------------------------------------------
    def save_etf_master(self, items: List[Dict[str, str]]) -> int:
        """
        자산 마스터 정보를 asset_master에 저장하거나 갱신합니다.
        기존 코드와의 호환을 위해 함수 이름은 save_etf_master를 유지합니다.
        """
        if not items:
            return 0

        saved = 0

        with get_db_session() as session:
            for item in items:
                ticker = str(item.get("ticker", "")).strip()
                name = str(item.get("name", "")).strip()

                if not ticker or not name:
                    continue

                market = str(item.get("market") or "KR").strip().upper()
                exchange = str(item.get("exchange") or "KRX").strip().upper()
                asset_type = str(item.get("asset_type") or "ETF").strip().upper()
                currency = str(item.get("currency") or "KRW").strip().upper()

                asset = (
                    session.query(AssetMaster)
                    .filter(AssetMaster.ticker == ticker)
                    .first()
                )

                if asset:
                    asset.name = name
                    asset.market = market
                    asset.exchange = exchange
                    asset.asset_type = asset_type
                    asset.currency = currency
                    asset.is_active = True
                    asset.updated_at = datetime.now()
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
        기존 코드와의 호환을 위해 함수 이름은 search_etf_master를 유지합니다.
        """
        clean_kw = str(keyword).strip()
        safe_limit = max(1, min(int(limit), 200))

        with get_db_session() as session:
            query = (
                session.query(AssetMaster)
                .filter(AssetMaster.is_active.is_(True))
            )

            if clean_kw:
                kw_pattern = f"%{clean_kw}%"

                query = query.filter(
                    (AssetMaster.ticker.ilike(kw_pattern))
                    | (AssetMaster.name.ilike(kw_pattern))
                )

            results = (
                query.order_by(
                    AssetMaster.market.asc(),
                    AssetMaster.name.asc(),
                )
                .limit(safe_limit)
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

    def get_etf_master(self, ticker: str) -> Optional[AssetMaster]:
        """
        종목코드로 활성 자산 마스터 한 건을 조회합니다.
        기존 코드와의 호환을 위해 함수 이름은 get_etf_master를 유지합니다.
        """
        clean_ticker = str(ticker).strip()

        if not clean_ticker:
            return None

        with get_db_session() as session:
            return (
                session.query(AssetMaster)
                .filter(
                    AssetMaster.ticker == clean_ticker,
                    AssetMaster.is_active.is_(True),
                )
                .first()
            )
