"""
ui/widgets/etf_search_dialog.py
국내 상장 ETF 종목 실시간 검색 및 선택 모달 다이얼로그.
- 종목명(한글/영문) 및 6자리 종목코드 실시간 부분 일치 검색
- 더블클릭 또는 Enter 키로 즉시 선택 및 자동 채움
"""

from __future__ import annotations
from typing import Optional, Tuple
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPushButton,
    QLabel,
    QMessageBox,
)
from PySide6.QtCore import Qt
from database.repository import Repository


class ETFSearchDialog(QDialog):
    """ETF 종목 실시간 검색 대화상자"""

    def __init__(self, repo: Repository, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.selected_item: Optional[Tuple[str, str]] = None  # (ticker, name)

        self.setWindowTitle("🔍 종목 검색 및 자동완성 (주식 / ETF)")
        self.setMinimumSize(540, 480)

        self._setup_ui()
        self._do_search()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # 상단 검색 바
        search_box = QHBoxLayout()
        search_lbl = QLabel("검색어:")
        search_lbl.setStyleSheet("font-weight: bold; color: #f8fafc;")
        search_box.addWidget(search_lbl)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("종목명 또는 코드 입력 (예: 삼성전자, SK하이닉스, TDF, 005930)...")
        self.search_input.textChanged.connect(self._do_search)
        self.search_input.returnPressed.connect(self._on_select)
        search_box.addWidget(self.search_input)

        layout.addLayout(search_box)

        # 검색 결과 카운트 라벨
        self.lbl_count = QLabel("검색 결과: 0건")
        self.lbl_count.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(self.lbl_count)

        # 검색 결과 테이블
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["종목코드", "종목명"])
        header = self.table.horizontalHeader()
        header.setSectionsMovable(True)
        header.setDragEnabled(True)
        header.setFirstSectionMovable(True)
        header.setStretchLastSection(True)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self.table)

        # 안내 문구
        tip = QLabel("💡 원하는 종목을 더블클릭하거나 선택 후 [선택] 버튼을 누르세요.")
        tip.setStyleSheet("color: #64748b; font-size: 11px;")
        layout.addWidget(tip)

        # 하단 조작 버튼
        btn_box = QHBoxLayout()
        btn_box.addStretch()

        btn_select = QPushButton("선택 (Enter)")
        btn_select.setProperty("class", "primary-btn")
        btn_select.clicked.connect(self._on_select)
        btn_box.addWidget(btn_select)

        btn_cancel = QPushButton("취소")
        btn_cancel.setProperty("class", "secondary-btn")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        layout.addLayout(btn_box)

    def _do_search(self):
        kw = self.search_input.text().strip()
        results = self.repo.search_etf_master(keyword=kw, limit=100)

        self.table.blockSignals(True)
        self.table.setRowCount(len(results))
        for row, it in enumerate(results):
            self.table.setItem(row, 0, QTableWidgetItem(it["ticker"]))
            self.table.setItem(row, 1, QTableWidgetItem(it["name"]))
        self.table.blockSignals(False)

        self.lbl_count.setText(f"검색 결과: {len(results)}건 (최대 100건 표시)")

        self.table.resizeColumnsToContents()
        cur_w0 = self.table.columnWidth(0)
        self.table.setColumnWidth(0, cur_w0 + 8)

        if len(results) > 0:
            self.table.selectRow(0)

    def _on_double_click(self, row: int, col: int):
        self._confirm_selection(row)

    def _on_select(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "안내", "추가할 ETF 종목을 표에서 선택해주세요.")
            return
        self._confirm_selection(row)

    def _confirm_selection(self, row: int):
        ticker_item = self.table.item(row, 0)
        name_item = self.table.item(row, 1)
        if ticker_item and name_item:
            self.selected_item = (ticker_item.text().strip(), name_item.text().strip())
            self.accept()
