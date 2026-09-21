"""
ui/transactions_page.py
거래내역 관리 화면 (프롬프트 48번, 56번, 57번 항목).
- 거래 조회, 추가, 수정, 삭제(CRUD)
- CSV 내보내기 및 가져오기
"""

from __future__ import annotations
from typing import Optional
from pathlib import Path
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPushButton,
    QDialog,
    QFormLayout,
    QLineEdit,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QMessageBox,
    QFileDialog,
    QLabel,
)
from PySide6.QtCore import Qt, Signal
from database.repository import Repository
from portfolio.transactions import TransactionManager


class TransactionDialog(QDialog):
    """거래 추가 및 수정을 위한 모달 대화상자 (종목코드 및 종목명 양방향 연동 지원)"""

    def __init__(
        self,
        tickers: list[str | tuple[str, str]],
        tx_data: dict | None = None,
        selected_account_id: int | None = None,
        repo: Repository | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.repo = repo
        self.setWindowTitle("거래 내역 " + ("수정" if tx_data else "추가"))
        self.setFixedWidth(430)

        # 1. 종목코드 및 종목명 리스트 구축 [(ticker, name), ...]
        self._etf_list: list[tuple[str, str]] = []
        seen = set()

        for it in tickers:
            if isinstance(it, (tuple, list)) and len(it) >= 2:
                code, name = str(it[0]).strip(), str(it[1]).strip()
            else:
                code = str(it).strip()
                name = ""
            if code and code not in seen:
                seen.add(code)
                self._etf_list.append((code, name))

        # repo를 통해 빈 이름 보완 및 마스터 DB 주요 종목 추가
        if self.repo:
            for i, (code, name) in enumerate(self._etf_list):
                if not name:
                    found = self.repo.search_etf_master(keyword=code, limit=1)
                    if found and found[0].get("ticker") == code:
                        self._etf_list[i] = (code, found[0].get("name", code))
                    else:
                        self._etf_list[i] = (code, code)

            master_etfs = self.repo.search_etf_master(keyword="", limit=200)
            for m in master_etfs:
                code = m.get("ticker", "").strip()
                name = m.get("name", "").strip()
                if code and code not in seen:
                    seen.add(code)
                    self._etf_list.append((code, name))
        else:
            for i, (code, name) in enumerate(self._etf_list):
                if not name:
                    self._etf_list[i] = (code, code)

        # 기존 수정 데이터의 ticker가 목록에 없으면 추가
        selected_ticker = tx_data.get("ticker") if tx_data else None
        if selected_ticker and selected_ticker not in seen:
            name = selected_ticker
            if self.repo:
                found = self.repo.search_etf_master(keyword=selected_ticker, limit=1)
                if found and found[0].get("ticker") == selected_ticker:
                    name = found[0].get("name", selected_ticker)
            self._etf_list.insert(0, (selected_ticker, name))
            seen.add(selected_ticker)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)
        form = QFormLayout()
        form.setSpacing(10)

        # 계좌 선택 콤보박스
        self.combo_account = QComboBox()
        if self.repo:
            accs = self.repo.get_accounts()
            for a in accs:
                self.combo_account.addItem(f"{a.account_name} ({a.broker or '증권'})", a.id)
            target_acc_id = tx_data.get("account_id") if tx_data else selected_account_id
            if target_acc_id:
                for idx in range(self.combo_account.count()):
                    if self.combo_account.itemData(idx) == target_acc_id:
                        self.combo_account.setCurrentIndex(idx)
                        break
        form.addRow("대상 계좌:", self.combo_account)

        self.input_date = QLineEdit(
            tx_data.get("date", datetime.now().strftime("%Y-%m-%d"))
            if tx_data
            else datetime.now().strftime("%Y-%m-%d")
        )
        form.addRow("거래일자 (YYYY-MM-DD):", self.input_date)

        # 종목코드 & 검색 버튼
        ticker_box = QHBoxLayout()
        self.combo_ticker = QComboBox()
        ticker_box.addWidget(self.combo_ticker, 1)

        btn_search = QPushButton("🔍 종목 검색")
        btn_search.setProperty("class", "secondary-btn")
        btn_search.clicked.connect(self._open_search_dialog)
        ticker_box.addWidget(btn_search)
        form.addRow("종목코드:", ticker_box)

        # 종목명 콤보박스 (종목코드와 양방향 연동)
        self.combo_name = QComboBox()
        form.addRow("종목명:", self.combo_name)

        # 콤보박스 데이터 초기화 및 연동 시그널 연결
        self._populate_combos(selected_ticker=selected_ticker)
        self.combo_ticker.currentIndexChanged.connect(self._on_ticker_changed)
        self.combo_name.currentIndexChanged.connect(self._on_name_changed)

        self.combo_type = QComboBox()
        self.combo_type.addItems(["BUY", "SELL", "DIVIDEND"])
        if tx_data:
            self.combo_type.setCurrentText(tx_data.get("type", "BUY"))
        form.addRow("거래유형:", self.combo_type)

        self.spin_qty = QSpinBox()
        self.spin_qty.setRange(0, 1000000)
        self.spin_qty.setValue(int(tx_data.get("quantity", 0)) if tx_data else 10)
        form.addRow("수량 (주):", self.spin_qty)

        self.spin_price = QDoubleSpinBox()
        self.spin_price.setRange(0.0, 10000000.0)
        self.spin_price.setValue(float(tx_data.get("price", 0.0)) if tx_data else 15000.0)
        form.addRow("단가 (원):", self.spin_price)

        self.spin_fee = QDoubleSpinBox()
        self.spin_fee.setRange(0.0, 1000000.0)
        self.spin_fee.setValue(float(tx_data.get("fee", 0.0)) if tx_data else 0.0)
        form.addRow("수수료 (원):", self.spin_fee)

        self.spin_tax = QDoubleSpinBox()
        self.spin_tax.setRange(0.0, 1000000.0)
        self.spin_tax.setValue(float(tx_data.get("tax", 0.0)) if tx_data else 0.0)
        form.addRow("제세금 (원):", self.spin_tax)

        self.input_memo = QLineEdit(tx_data.get("memo", "") if tx_data else "")
        form.addRow("메모:", self.input_memo)

        layout.addLayout(form)

        btn_box = QHBoxLayout()
        btn_box.addStretch()
        btn_save = QPushButton("저장")
        btn_save.setProperty("class", "primary-btn")
        btn_save.clicked.connect(self.accept)

        btn_cancel = QPushButton("취소")
        btn_cancel.setProperty("class", "secondary-btn")
        btn_cancel.clicked.connect(self.reject)

        btn_box.addWidget(btn_save)
        btn_box.addWidget(btn_cancel)
        layout.addLayout(btn_box)

    def _populate_combos(self, selected_ticker: str | None = None):
        self.combo_ticker.blockSignals(True)
        self.combo_name.blockSignals(True)
        self.combo_ticker.clear()
        self.combo_name.clear()

        select_idx = 0
        for idx, (code, name) in enumerate(self._etf_list):
            self.combo_ticker.addItem(code, code)
            self.combo_name.addItem(name, code)
            if selected_ticker and code == selected_ticker:
                select_idx = idx

        if self._etf_list:
            self.combo_ticker.setCurrentIndex(select_idx)
            self.combo_name.setCurrentIndex(select_idx)

        self.combo_ticker.blockSignals(False)
        self.combo_name.blockSignals(False)

    def _on_ticker_changed(self, index: int):
        if index < 0 or index >= self.combo_name.count():
            return
        self.combo_name.blockSignals(True)
        self.combo_name.setCurrentIndex(index)
        self.combo_name.blockSignals(False)

    def _on_name_changed(self, index: int):
        if index < 0 or index >= self.combo_ticker.count():
            return
        self.combo_ticker.blockSignals(True)
        self.combo_ticker.setCurrentIndex(index)
        self.combo_ticker.blockSignals(False)

    def _open_search_dialog(self):
        from ui.widgets.etf_search_dialog import ETFSearchDialog
        if not self.repo:
            return
        dlg = ETFSearchDialog(self.repo, self)
        if dlg.exec() == QDialog.Accepted and dlg.selected_item:
            code, name = dlg.selected_item
            found_idx = -1
            for idx, (c, _) in enumerate(self._etf_list):
                if c == code:
                    found_idx = idx
                    break
            if found_idx == -1:
                self._etf_list.insert(0, (code, name))
                self._populate_combos(selected_ticker=code)
            else:
                self.combo_ticker.setCurrentIndex(found_idx)
                self.combo_name.setCurrentIndex(found_idx)

    def get_data(self) -> dict:
        acc_id = self.combo_account.currentData() if hasattr(self, "combo_account") and self.combo_account.count() > 0 else None
        return {
            "account_id": acc_id,
            "date": self.input_date.text().strip(),
            "ticker": self.combo_ticker.currentData() or self.combo_ticker.currentText().strip(),
            "type": self.combo_type.currentText().strip(),
            "quantity": self.spin_qty.value(),
            "price": self.spin_price.value(),
            "fee": self.spin_fee.value(),
            "tax": self.spin_tax.value(),
            "memo": self.input_memo.text().strip(),
        }


class TransactionsPage(QWidget):
    data_changed = Signal()

    def __init__(self, repo: Repository, available_tickers: list[str], parent=None):
        super().__init__(parent)
        self.repo = repo
        self.tickers = available_tickers
        self.tm = TransactionManager(repo)
        self.current_account_id: int | None = None

        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(16)

        # 상단 툴바
        toolbar = QHBoxLayout()
        btn_add = QPushButton("＋ 거래 추가")
        btn_add.setProperty("class", "primary-btn")
        btn_add.clicked.connect(self._add_transaction)
        toolbar.addWidget(btn_add)

        btn_edit = QPushButton("선택 수정")
        btn_edit.setProperty("class", "secondary-btn")
        btn_edit.clicked.connect(self._edit_transaction)
        toolbar.addWidget(btn_edit)

        btn_del = QPushButton("선택 삭제")
        btn_del.setProperty("class", "danger-btn")
        btn_del.clicked.connect(self._delete_transaction)
        toolbar.addWidget(btn_del)

        toolbar.addStretch()

        btn_export = QPushButton("CSV 내보내기")
        btn_export.setProperty("class", "secondary-btn")
        btn_export.clicked.connect(self._export_csv)
        toolbar.addWidget(btn_export)

        btn_import = QPushButton("CSV 가져오기")
        btn_import.setProperty("class", "secondary-btn")
        btn_import.clicked.connect(self._import_csv)
        toolbar.addWidget(btn_import)

        main_layout.addLayout(toolbar)

        # 거래 목록 테이블
        self.table = QTableWidget()
        headers = ["ID", "계좌", "일자", "종목코드", "거래구분", "수량", "단가", "거래총액", "수수료", "제세금", "메모"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        header = self.table.horizontalHeader()
        header.setSectionsMovable(True)
        header.setDragEnabled(True)
        header.setFirstSectionMovable(True)
        header.setSectionResizeMode(QHeaderView.Interactive)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        main_layout.addWidget(self.table)

    def refresh(self, account_id: Optional[int] = None):
        self.current_account_id = account_id
        txs = self.repo.get_transactions(account_id=account_id)
        acc_map = {a.id: a.account_name for a in self.repo.get_accounts()}
        self.table.setRowCount(len(txs))

        for row, tx in enumerate(reversed(txs)):
            total_amt = (tx.quantity * tx.price) + (tx.fee or 0) + (tx.tax or 0)
            acc_name = acc_map.get(tx.account_id, "기본")

            self.table.setItem(row, 0, QTableWidgetItem(str(tx.id)))
            acc_item = QTableWidgetItem(acc_name)
            acc_item.setData(Qt.UserRole, tx.account_id)
            self.table.setItem(row, 1, acc_item)
            self.table.setItem(row, 2, QTableWidgetItem(tx.transaction_date))
            self.table.setItem(row, 3, QTableWidgetItem(tx.ticker))

            type_item = QTableWidgetItem(tx.transaction_type)
            if tx.transaction_type == "BUY":
                type_item.setForeground(Qt.red)
            elif tx.transaction_type == "SELL":
                type_item.setForeground(Qt.blue)
            self.table.setItem(row, 4, type_item)

            self.table.setItem(row, 5, QTableWidgetItem(f"{tx.quantity:,}주"))
            self.table.setItem(row, 6, QTableWidgetItem(f"{tx.price:,.0f}원"))
            self.table.setItem(row, 7, QTableWidgetItem(f"{total_amt:,.0f}원"))
            self.table.setItem(row, 8, QTableWidgetItem(f"{tx.fee:,.0f}원"))
            self.table.setItem(row, 9, QTableWidgetItem(f"{tx.tax:,.0f}원"))
            self.table.setItem(row, 10, QTableWidgetItem(tx.memo or ""))

        self.table.resizeColumnsToContents()
        for col in range(self.table.columnCount()):
            cur_w = self.table.columnWidth(col)
            if col == 1:  # 계좌
                self.table.setColumnWidth(col, max(cur_w + 10, 110))
            elif col == 10:  # 메모
                self.table.setColumnWidth(col, max(cur_w + 10, 100))
            else:
                self.table.setColumnWidth(col, cur_w + 6)

    def _add_transaction(self):
        dlg = TransactionDialog(
            self.tickers,
            selected_account_id=self.current_account_id,
            repo=self.repo,
            parent=self,
        )
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            self.repo.add_transaction(
                account_id=data.get("account_id"),
                transaction_date=data["date"],
                ticker=data["ticker"],
                transaction_type=data["type"],
                quantity=data["quantity"],
                price=data["price"],
                fee=data["fee"],
                tax=data["tax"],
                memo=data["memo"],
            )
            self.refresh(account_id=self.current_account_id)
            self.data_changed.emit()

    def _edit_transaction(self):
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            QMessageBox.information(self, "안내", "수정할 거래 행을 선택해주세요.")
            return

        row = selected[0].row()
        tx_id = int(self.table.item(row, 0).text())
        account_id = self.table.item(row, 1).data(Qt.UserRole)
        tx_date = self.table.item(row, 2).text()
        ticker = self.table.item(row, 3).text()
        tx_type = self.table.item(row, 4).text()
        qty = int(self.table.item(row, 5).text().replace("주", "").replace(",", ""))
        price = float(self.table.item(row, 6).text().replace("원", "").replace(",", ""))
        fee = float(self.table.item(row, 8).text().replace("원", "").replace(",", ""))
        tax = float(self.table.item(row, 9).text().replace("원", "").replace(",", ""))
        memo = self.table.item(row, 10).text()

        tx_data = {
            "account_id": account_id,
            "date": tx_date,
            "ticker": ticker,
            "type": tx_type,
            "quantity": qty,
            "price": price,
            "fee": fee,
            "tax": tax,
            "memo": memo,
        }

        dlg = TransactionDialog(
            self.tickers,
            tx_data=tx_data,
            selected_account_id=account_id,
            repo=self.repo,
            parent=self,
        )
        if dlg.exec() == QDialog.Accepted:
            updated = dlg.get_data()
            self.repo.update_transaction(
                tx_id=tx_id,
                account_id=updated.get("account_id"),
                transaction_date=updated["date"],
                ticker=updated["ticker"],
                transaction_type=updated["type"],
                quantity=updated["quantity"],
                price=updated["price"],
                fee=updated["fee"],
                tax=updated["tax"],
                memo=updated["memo"],
            )
            self.refresh(account_id=self.current_account_id)
            self.data_changed.emit()

    def _delete_transaction(self):
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            QMessageBox.information(self, "안내", "삭제할 거래 행을 선택해주세요.")
            return

        row = selected[0].row()
        tx_id = int(self.table.item(row, 0).text())

        reply = QMessageBox.question(
            self,
            "거래 삭제 확인",
            f"선택한 거래(ID: {tx_id})를 정말 삭제하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.repo.delete_transaction(tx_id)
            self.refresh(account_id=self.current_account_id)
            self.data_changed.emit()

    def _export_csv(self):
        try:
            exported_path = self.tm.export_to_csv(account_id=self.current_account_id)
            QMessageBox.information(self, "내보내기 완료", f"거래내역이 저장되었습니다:\n{exported_path}")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"CSV 내보내기 실패: {e}")

    def _import_csv(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "CSV 파일 선택", "", "CSV Files (*.csv)")
        if not file_path:
            return
        try:
            cnt = self.tm.import_from_csv(Path(file_path), default_account_id=self.current_account_id)
            QMessageBox.information(self, "가져오기 완료", f"{cnt}건의 거래내역을 성공적으로 가져왔습니다.")
            self.refresh(account_id=self.current_account_id)
            self.data_changed.emit()
        except Exception as e:
            QMessageBox.critical(self, "오류", f"CSV 가져오기 실패: {e}")
