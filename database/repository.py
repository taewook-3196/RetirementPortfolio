"""
database/repository.py
데이터베이스 접근 및 CRUD 함수를 제공합니다.
- 중복 방지 기반의 가격 데이터 저장 (upsert/insert-ignore)
- 종목별 가격 이력 및 최근 3개월 고점 조회
- 거래내역(매수/매도) 및 분배금 CRUD
- 매수 추천 결과 기록 및 조회
- SQLite 안전한 Backup API 기반의 원자적 데이터베이스 백업 및 복원
"""

from __future__ import annotations
import sqlite3
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy import desc, func, and_
from sqlalchemy.orm import Session
from core.paths import get_database_path, get_backup_dir
from core.config import ETFConfig, load_config
from database.connection import get_db_session, get_engine, init_db
from database.models import Price, Transaction, Dividend, RecommendationLog, ETFMaster, Account, AccountTarget
from data.etf_seeds import POPULAR_ETF_SEEDS


class Repository:
    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path) if db_path else get_database_path()
        init_db(self.db_path)
        self._ensure_seed_etf_master()

    def _ensure_seed_etf_master(self):
        """기본 종목 마스터 시드 데이터를 DB에 안전하게 병합합니다."""
        try:
            self.save_etf_master(POPULAR_ETF_SEEDS)
        except Exception:
            pass

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
        with get_db_session(self.db_path) as session:
            for item in price_dicts:
                date_str = str(item.get("date", "")).replace("-", "")
                ticker = str(item.get("ticker", "")).strip()
                if not date_str or not ticker:
                    continue

                existing = (
                    session.query(Price)
                    .filter(Price.date == date_str, Price.ticker == ticker)
                    .first()
                )
                if existing:
                    existing.name = item.get("name", existing.name)
                    existing.open_price = float(item.get("open_price", existing.open_price))
                    existing.high_price = float(item.get("high_price", existing.high_price))
                    existing.low_price = float(item.get("low_price", existing.low_price))
                    existing.close_price = float(item.get("close_price", existing.close_price))
                    existing.nav = float(item.get("nav", existing.nav or 0.0))
                    existing.volume = int(item.get("volume", existing.volume))
                    existing.trading_value = float(item.get("trading_value", existing.trading_value))
                else:
                    new_p = Price(
                        date=date_str,
                        ticker=ticker,
                        name=item.get("name", ""),
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
        with get_db_session(self.db_path) as session:
            query = session.query(Price).filter(Price.ticker == ticker, Price.close_price > 0)
            if start_date:
                query = query.filter(Price.date >= start_date.replace("-", ""))
            if end_date:
                query = query.filter(Price.date <= end_date.replace("-", ""))
            query = query.order_by(Price.date.asc())
            if limit:
                # 최신 기준 limit개 조회 후 오름차순 정렬
                recent_query = (
                    session.query(Price)
                    .filter(Price.ticker == ticker, Price.close_price > 0)
                    .order_by(Price.date.desc())
                    .limit(limit)
                )
                prices = list(recent_query)
                prices.reverse()
                return prices
            return list(query.all())

    def get_latest_price(self, ticker: str) -> Optional[Price]:
        """특정 종목의 가장 최신 가격 데이터를 조회합니다 (0원 미거래일 제외)."""
        with get_db_session(self.db_path) as session:
            return (
                session.query(Price)
                .filter(Price.ticker == ticker, Price.close_price > 0)
                .order_by(Price.date.desc())
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
        with get_db_session(self.db_path) as session:
            latest = self.get_latest_price(ticker)
            if not latest:
                return (0.0, "")

            ref_date_str = as_of_date.replace("-", "") if as_of_date else latest.date
            ref_dt = datetime.strptime(ref_date_str, "%Y%m%d")
            start_dt = ref_dt - timedelta(days=93)  # 약 3개월
            start_date_str = start_dt.strftime("%Y%m%d")

            query = session.query(Price).filter(
                Price.ticker == ticker,
                Price.close_price > 0,
                Price.date >= start_date_str,
            )
            if exclude_today:
                query = query.filter(Price.date < ref_date_str)
            else:
                query = query.filter(Price.date <= ref_date_str)

            high_row = query.order_by(Price.close_price.desc(), Price.date.desc()).first()
            if high_row:
                return (high_row.close_price, high_row.date)
            return (latest.close_price, latest.date)

    # -------------------------------------------------------------
    # 계좌 (Account) 관리
    # -------------------------------------------------------------
    def get_accounts(self) -> List[Account]:
        """등록된 모든 계좌를 조회합니다 (기본 계좌 우선, 그 다음 ID순)."""
        with get_db_session(self.db_path) as session:
            return list(session.query(Account).order_by(Account.is_default.desc(), Account.id.asc()).all())

    def get_account(self, account_id: int) -> Optional[Account]:
        """특정 계좌 정보를 조회합니다."""
        with get_db_session(self.db_path) as session:
            return session.query(Account).filter(Account.id == account_id).first()

    def get_default_account(self) -> Optional[Account]:
        """기본 계좌를 조회합니다."""
        with get_db_session(self.db_path) as session:
            acc = session.query(Account).filter(Account.is_default == 1).first()
            if not acc:
                acc = session.query(Account).first()
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
        """신규 계좌를 생성합니다."""
        with get_db_session(self.db_path) as session:
            if is_default:
                session.query(Account).update({Account.is_default: 0})
            acc = Account(
                account_name=account_name.strip(),
                account_number=account_number.strip(),
                broker=broker.strip(),
                initial_capital=float(initial_capital),
                base_monthly=float(base_monthly),
                max_additional_monthly=float(max_additional_monthly),
                buy_cycle_type=buy_cycle_type.strip() if buy_cycle_type else "monthly",
                buy_cycle_detail=buy_cycle_detail.strip() if buy_cycle_detail else "25",
                is_default=1 if is_default else 0,
                memo=memo.strip(),
            )
            session.add(acc)
            session.flush()
            session.refresh(acc)

            # 신규 계좌 초기 목표 비중 시딩
            from core.config import load_config
            cfg = load_config()
            for etf in cfg.etfs:
                session.add(
                    AccountTarget(
                        account_id=acc.id,
                        ticker=etf.ticker,
                        name=etf.name,
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
        """계좌 정보를 수정합니다."""
        with get_db_session(self.db_path) as session:
            acc = session.query(Account).filter(Account.id == account_id).first()
            if not acc:
                return False
            if is_default:
                session.query(Account).filter(Account.id != account_id).update({Account.is_default: 0})
            acc.account_name = account_name.strip()
            acc.account_number = account_number.strip()
            acc.broker = broker.strip()
            acc.initial_capital = float(initial_capital)
            acc.base_monthly = float(base_monthly)
            acc.max_additional_monthly = float(max_additional_monthly)
            acc.buy_cycle_type = buy_cycle_type.strip() if buy_cycle_type else "monthly"
            acc.buy_cycle_detail = buy_cycle_detail.strip() if buy_cycle_detail else "25"
            acc.is_default = 1 if is_default else 0
            acc.memo = memo.strip()
            acc.updated_at = datetime.now()
            return True

    def set_default_account(self, account_id: int) -> bool:
        """기본 계좌로 지정합니다."""
        with get_db_session(self.db_path) as session:
            session.query(Account).update({Account.is_default: 0})
            acc = session.query(Account).filter(Account.id == account_id).first()
            if not acc:
                return False
            acc.is_default = 1
            return True

    def delete_account(self, account_id: int) -> bool:
        """계좌를 삭제합니다. 연관 거래/분배금은 유지(account_id=NULL) 또는 자동 처리됩니다."""
        with get_db_session(self.db_path) as session:
            acc = session.query(Account).filter(Account.id == account_id).first()
            if not acc:
                return False
            was_default = acc.is_default
            session.query(AccountTarget).filter(AccountTarget.account_id == account_id).delete()
            session.delete(acc)
            if was_default:
                remaining = session.query(Account).filter(Account.id != account_id).first()
                if remaining:
                    remaining.is_default = 1
            return True

    def get_account_targets(self, account_id: Optional[int] = None) -> List[ETFConfig]:
        """
        계좌별 목표 비중 목록을 반환합니다.
        account_id가 None이면 모든 계좌의 목표 비중을 각 계좌의 자본금 한도 비율로 가중 합산하여 통합 반환합니다.
        해당 계좌의 저장된 목표 비중이 없을 경우 기본 etfs 목록을 기본값으로 반환합니다.
        """
        with get_db_session(self.db_path) as session:
            if account_id is not None:
                rows = (
                    session.query(AccountTarget)
                    .filter(AccountTarget.account_id == account_id)
                    .order_by(AccountTarget.id.asc())
                    .all()
                )
                if rows:
                    return [
                        ETFConfig(
                            ticker=r.ticker,
                            name=r.name or r.ticker,
                            target_weight=r.target_weight,
                            dividend_yield=r.dividend_yield,
                        )
                        for r in rows
                    ]
                cfg = load_config()
                return list(cfg.etfs)

            # account_id is None (전체 계좌 통합)
            accounts = session.query(Account).all()
            if not accounts:
                cfg = load_config()
                return list(cfg.etfs)

            if len(accounts) == 1:
                rows = (
                    session.query(AccountTarget)
                    .filter(AccountTarget.account_id == accounts[0].id)
                    .order_by(AccountTarget.id.asc())
                    .all()
                )
                if rows:
                    return [
                        ETFConfig(
                            ticker=r.ticker,
                            name=r.name or r.ticker,
                            target_weight=r.target_weight,
                            dividend_yield=r.dividend_yield,
                        )
                        for r in rows
                    ]
                cfg = load_config()
                return list(cfg.etfs)

            # 다중 계좌: 각 계좌의 자본금(initial_capital) 비율대로 가중 합산
            total_cap = sum(max(0.0, a.initial_capital) for a in accounts)
            combined: Dict[str, Dict[str, Any]] = {}

            for acc in accounts:
                weight_factor = (acc.initial_capital / total_cap) if total_cap > 0 else (1.0 / len(accounts))
                rows = (
                    session.query(AccountTarget)
                    .filter(AccountTarget.account_id == acc.id)
                    .order_by(AccountTarget.id.asc())
                    .all()
                )
                acc_targets = rows if rows else [
                    AccountTarget(
                        account_id=acc.id,
                        ticker=e.ticker,
                        name=e.name,
                        target_weight=e.target_weight,
                        dividend_yield=e.dividend_yield,
                    )
                    for e in load_config().etfs
                ]

                for r in acc_targets:
                    if r.ticker not in combined:
                        combined[r.ticker] = {
                            "ticker": r.ticker,
                            "name": r.name or r.ticker,
                            "target_weight": 0.0,
                            "dividend_yield": 0.0,
                        }
                    combined[r.ticker]["target_weight"] += r.target_weight * weight_factor
                    combined[r.ticker]["dividend_yield"] += (r.dividend_yield or 0.0) * weight_factor
                    if not combined[r.ticker]["name"] and r.name:
                        combined[r.ticker]["name"] = r.name

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
        """계좌의 목표 비중 목록을 저장합니다."""
        with get_db_session(self.db_path) as session:
            session.query(AccountTarget).filter(AccountTarget.account_id == account_id).delete()
            for t in targets:
                session.add(
                    AccountTarget(
                        account_id=account_id,
                        ticker=t.ticker,
                        name=t.name,
                        target_weight=t.target_weight,
                        dividend_yield=t.dividend_yield,
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
        """거래 내역을 추가합니다."""
        with get_db_session(self.db_path) as session:
            if account_id is None:
                def_acc = session.query(Account).filter(Account.is_default == 1).first()
                if not def_acc:
                    def_acc = session.query(Account).first()
                if def_acc:
                    account_id = def_acc.id

            tx = Transaction(
                account_id=account_id,
                transaction_date=transaction_date,
                ticker=ticker,
                transaction_type=transaction_type.upper(),
                quantity=quantity,
                price=price,
                fee=fee,
                tax=tax,
                memo=memo,
            )
            session.add(tx)
            session.flush()
            session.refresh(tx)
            return tx

    def get_transactions(
        self, ticker: Optional[str] = None, account_id: Optional[int] = None
    ) -> List[Transaction]:
        """전체, 종목별 또는 계좌별 거래 내역을 일자순으로 조회합니다."""
        with get_db_session(self.db_path) as session:
            query = session.query(Transaction)
            if ticker:
                query = query.filter(Transaction.ticker == ticker)
            if account_id is not None:
                query = query.filter(Transaction.account_id == account_id)
            return list(query.order_by(Transaction.transaction_date.asc(), Transaction.id.asc()).all())

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
        """거래 내역을 수정합니다."""
        with get_db_session(self.db_path) as session:
            tx = session.query(Transaction).filter(Transaction.id == tx_id).first()
            if not tx:
                return False
            tx.transaction_date = transaction_date
            tx.ticker = ticker
            tx.transaction_type = transaction_type.upper()
            tx.quantity = quantity
            tx.price = price
            tx.fee = fee
            tx.tax = tax
            tx.memo = memo
            if account_id is not None:
                tx.account_id = account_id
            tx.updated_at = datetime.now()
            return True

    def delete_transaction(self, tx_id: int) -> bool:
        """거래 내역을 삭제합니다."""
        with get_db_session(self.db_path) as session:
            tx = session.query(Transaction).filter(Transaction.id == tx_id).first()
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
        """분배금 내역을 추가합니다."""
        net = net_amount if net_amount is not None else (gross_amount - tax)
        with get_db_session(self.db_path) as session:
            if account_id is None:
                def_acc = session.query(Account).filter(Account.is_default == 1).first()
                if not def_acc:
                    def_acc = session.query(Account).first()
                if def_acc:
                    account_id = def_acc.id

            div = Dividend(
                account_id=account_id,
                dividend_date=dividend_date,
                ticker=ticker,
                gross_amount=gross_amount,
                tax=tax,
                net_amount=net,
            )
            session.add(div)
            session.flush()
            session.refresh(div)
            return div

    def get_dividends(
        self, ticker: Optional[str] = None, account_id: Optional[int] = None
    ) -> List[Dividend]:
        """분배금 수령 내역을 조회합니다."""
        with get_db_session(self.db_path) as session:
            query = session.query(Dividend)
            if ticker:
                query = query.filter(Dividend.ticker == ticker)
            if account_id is not None:
                query = query.filter(Dividend.account_id == account_id)
            return list(query.order_by(Dividend.dividend_date.asc(), Dividend.id.asc()).all())

    # -------------------------------------------------------------
    # 매수 추천 기록 (RecommendationLog) 관리
    # -------------------------------------------------------------
    def save_recommendations(self, rec_list: List[Dict[str, Any]]) -> None:
        """매수 추천 결과를 저장합니다."""
        with get_db_session(self.db_path) as session:
            for item in rec_list:
                log = RecommendationLog(
                    recommendation_date=item.get("date", datetime.now().strftime("%Y-%m-%d")),
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
                    expected_weight_after=float(item.get("expected_weight_after", 0.0)),
                    reason=item.get("reason", ""),
                )
                session.add(log)

    def get_latest_recommendations(self) -> List[RecommendationLog]:
        """가장 최근에 기록된 매수 추천 결과를 조회합니다."""
        with get_db_session(self.db_path) as session:
            latest_date_row = (
                session.query(RecommendationLog.recommendation_date)
                .order_by(RecommendationLog.recommendation_date.desc())
                .first()
            )
            if not latest_date_row:
                return []
            latest_date = latest_date_row[0]
            return list(
                session.query(RecommendationLog)
                .filter(RecommendationLog.recommendation_date == latest_date)
                .all()
            )

    # -------------------------------------------------------------
    # SQLite Backup & Restore API (13번 항목)
    # -------------------------------------------------------------
    def backup_database(self, destination_dir: Optional[Path] = None) -> Path:
        """
        SQLite native backup API를 활용하여 안전하고 원자적으로 DB 백업을 수행합니다.
        생성 파일 예: backup/portfolio_20260916_180000.db
        """
        backup_dir = destination_dir or get_backup_dir()
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"portfolio_{timestamp}.db"

        # SQLite 온라인 백업 API 사용 (잠금 충돌 없이 안전 복제)
        src_conn = sqlite3.connect(self.db_path.as_posix())
        dst_conn = sqlite3.connect(backup_file.as_posix())
        try:
            with dst_conn:
                src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
            src_conn.close()

        return backup_file

    def restore_database(self, backup_file: Path) -> bool:
        """
        백업 파일로부터 portfolio.db를 안전하게 복원합니다.
        """
        if not backup_file.exists():
            raise FileNotFoundError(f"백업 파일을 찾을 수 없습니다: {backup_file}")

        # 복원 대상 연결
        src_conn = sqlite3.connect(backup_file.as_posix())
        dst_conn = sqlite3.connect(self.db_path.as_posix())
        try:
            with dst_conn:
                src_conn.backup(dst_conn)
            return True
        finally:
            dst_conn.close()
            src_conn.close()

    # -------------------------------------------------------------
    # ETF 마스터 (ETFMaster) 관리 및 검색
    # -------------------------------------------------------------
    def save_etf_master(self, items: List[Dict[str, str]]) -> int:
        """ETF 마스터 목록(종목코드, 종목명)을 일괄 저장/갱신합니다."""
        if not items:
            return 0
        saved = 0
        with get_db_session(self.db_path) as session:
            for it in items:
                ticker = str(it.get("ticker", "")).strip()
                name = str(it.get("name", "")).strip()
                if not ticker or not name:
                    continue
                obj = session.query(ETFMaster).filter(ETFMaster.ticker == ticker).first()
                if obj:
                    if obj.name != name:
                        obj.name = name
                        obj.updated_at = datetime.now()
                else:
                    session.add(ETFMaster(ticker=ticker, name=name))
                saved += 1
        return saved

    def search_etf_master(self, keyword: str = "", limit: int = 50) -> List[Dict[str, str]]:
        """
        키워드로 종목코드 또는 종목명을 검색합니다.
        keyword가 빈 문자열이면 전체/기본 목록을 반환합니다.
        """
        clean_kw = keyword.strip()
        with get_db_session(self.db_path) as session:
            query = session.query(ETFMaster)
            if clean_kw:
                kw_pattern = f"%{clean_kw}%"
                query = query.filter(
                    (ETFMaster.ticker.like(kw_pattern)) | (ETFMaster.name.like(kw_pattern))
                )
            results = query.order_by(ETFMaster.name.asc()).limit(limit).all()
            return [{"ticker": r.ticker, "name": r.name} for r in results]

    def get_etf_master(self, ticker: str) -> Optional[ETFMaster]:
        """종목코드로 ETF 마스터 단건을 조회합니다."""
        clean_ticker = str(ticker).strip()
        with get_db_session(self.db_path) as session:
            return session.query(ETFMaster).filter(ETFMaster.ticker == clean_ticker).first()

