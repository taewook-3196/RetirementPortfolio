"""
portfolio/transactions.py
거래 내역 관리 및 CSV 내보내기/가져오기 기능 (프롬프트 56번, 57번 항목).
"""

from __future__ import annotations
import csv
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from core.paths import get_export_dir, get_import_dir
from database.repository import Repository
from database.models import Transaction


class TransactionManager:
    def __init__(self, repo: Repository):
        self.repo = repo

    def export_to_csv(
        self, export_path: Optional[Path] = None, account_id: Optional[int] = None
    ) -> Path:
        """모든 또는 특정 계좌의 거래 내역을 CSV 파일로 내보냅니다."""
        target_dir = get_export_dir()
        if not export_path:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            prefix = f"transactions_acc{account_id}_" if account_id else "transactions_"
            export_path = target_dir / f"{prefix}{ts}.csv"

        transactions = self.repo.get_transactions(account_id=account_id)
        acc_map = {a.id: a.account_name for a in self.repo.get_accounts()}

        headers = [
            "id",
            "account_id",
            "account_name",
            "transaction_date",
            "ticker",
            "transaction_type",
            "quantity",
            "price",
            "fee",
            "tax",
            "memo",
        ]

        with open(export_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for tx in transactions:
                writer.writerow([
                    tx.id,
                    tx.account_id or "",
                    acc_map.get(tx.account_id, ""),
                    tx.transaction_date,
                    tx.ticker,
                    tx.transaction_type,
                    tx.quantity,
                    tx.price,
                    tx.fee,
                    tx.tax,
                    tx.memo,
                ])

        return export_path

    def import_from_csv(
        self, import_file_path: Path, default_account_id: Optional[int] = None
    ) -> int:
        """CSV 파일로부터 거래 내역을 읽어 DB에 추가합니다. 계좌 정보가 있으면 해당 계좌에 매핑합니다."""
        if not import_file_path.exists():
            raise FileNotFoundError(f"가져올 파일을 찾을 수 없습니다: {import_file_path}")

        accounts = self.repo.get_accounts()
        acc_by_name = {a.account_name: a.id for a in accounts}
        acc_ids = {a.id for a in accounts}
        fallback_acc = default_account_id or (accounts[0].id if accounts else None)

        count = 0
        with open(import_file_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                tx_date = row.get("transaction_date", "").strip()
                ticker = row.get("ticker", "").strip()
                tx_type = row.get("transaction_type", "BUY").strip().upper()
                qty = int(row.get("quantity", 0))
                price = float(row.get("price", 0.0))
                fee = float(row.get("fee", 0.0) or 0.0)
                tax = float(row.get("tax", 0.0) or 0.0)
                memo = row.get("memo", "").strip()

                # 계좌 매핑
                row_acc_id = row.get("account_id", "").strip()
                row_acc_name = row.get("account_name", "").strip()
                target_acc_id = None

                if row_acc_id and row_acc_id.isdigit() and int(row_acc_id) in acc_ids:
                    target_acc_id = int(row_acc_id)
                elif row_acc_name and row_acc_name in acc_by_name:
                    target_acc_id = acc_by_name[row_acc_name]
                else:
                    target_acc_id = fallback_acc

                if tx_date and ticker and qty > 0 and price > 0:
                    self.repo.add_transaction(
                        account_id=target_acc_id,
                        transaction_date=tx_date,
                        ticker=ticker,
                        transaction_type=tx_type,
                        quantity=qty,
                        price=price,
                        fee=fee,
                        tax=tax,
                        memo=memo,
                    )
                    count += 1
        return count
