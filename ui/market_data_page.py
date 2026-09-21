"""
ui/market_data_page.py
시장 데이터 화면 (프롬프트 49번 항목).
- ETF 종목 선택 (포트폴리오 종목 및 관심 종목) 및 기간(3개월, 6개월, 1년, 전체) 필터링
- 최근 가격 추이 및 3개월 고점 라인 차트 (마우스 호버 실시간 툴팁 지원)
- 일별 시세(시가, 고가, 저가, 종가, NAV, 거래량, 거래대금) 테이블
- 관심 종목 추가/삭제/관리 다이얼로그
"""

from __future__ import annotations
from typing import List
from PySide6.QtWidgets import (
    QWidget,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QComboBox,
    QLabel,
    QFrame,
    QPushButton,
    QMessageBox,
)
from PySide6.QtCore import Qt, Signal
from ui.widgets.charts import PriceTrendChart
from services.market_data_service import MarketDataService
from core.config import AppConfig, WatchlistConfig, save_config, load_config
from ui.widgets.etf_search_dialog import ETFSearchDialog
from database.repository import Repository


class WatchlistDialog(QDialog):
    """관심 종목(Watchlist) 관리 모달 다이얼로그"""

    def __init__(self, config: AppConfig, repo: Repository, parent=None):
        super().__init__(parent)
        self.config = config
        self.repo = repo
        self.setWindowTitle("관심 종목 관리")
        self.setMinimumSize(480, 420)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        desc = QLabel(
            "포트폴리오 편입 여부와 관계없이 시장 가격 및 차트를 모니터링할 관심 ETF를 관리합니다."
        )
        desc.setStyleSheet("color: #94a3b8; font-size: 12px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # 상단 조작 버튼
        btn_box = QHBoxLayout()
        btn_search = QPushButton("🔍 종목 검색 추가")
        btn_search.setProperty("class", "primary-btn")
        btn_search.clicked.connect(self._open_search_dialog)
        btn_box.addWidget(btn_search)

        btn_add = QPushButton("＋ 직접 입력")
        btn_add.setProperty("class", "secondary-btn")
        btn_add.clicked.connect(self._add_row)
        btn_box.addWidget(btn_add)

        btn_del = QPushButton("－ 선택 삭제")
        btn_del.setProperty("class", "danger-btn")
        btn_del.clicked.connect(self._del_row)
        btn_box.addWidget(btn_del)

        btn_box.addStretch()
        layout.addLayout(btn_box)

        # 관심종목 테이블
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["종목코드", "종목명"])
        header = self.table.horizontalHeader()
        header.setSectionsMovable(True)
        header.setDragEnabled(True)
        header.setFirstSectionMovable(True)
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # 기존 관심종목 로드
        current_watchlist = getattr(self.config, "watchlist", [])
        self.table.setRowCount(len(current_watchlist))
        for row, item in enumerate(current_watchlist):
            self.table.setItem(row, 0, QTableWidgetItem(item.ticker))
            self.table.setItem(row, 1, QTableWidgetItem(item.name))

        self._adjust_columns()
        layout.addWidget(self.table)

        # 하단 저장/닫기 버튼
        bottom_box = QHBoxLayout()
        bottom_box.addStretch()

        btn_save = QPushButton("💾 저장")
        btn_save.setProperty("class", "primary-btn")
        btn_save.clicked.connect(self._save_watchlist)
        bottom_box.addWidget(btn_save)

        btn_close = QPushButton("닫기")
        btn_close.setProperty("class", "secondary-btn")
        btn_close.clicked.connect(self.reject)
        bottom_box.addWidget(btn_close)

        layout.addLayout(bottom_box)

    def _adjust_columns(self):
        self.table.resizeColumnsToContents()
        cur_w0 = self.table.columnWidth(0)
        self.table.setColumnWidth(0, cur_w0 + 8)

    def _open_search_dialog(self):
        dlg = ETFSearchDialog(self.repo, self)
        if dlg.exec() == QDialog.Accepted and dlg.selected_item:
            ticker, name = dlg.selected_item
            for r in range(self.table.rowCount()):
                item = self.table.item(r, 0)
                if item and item.text().strip() == ticker:
                    QMessageBox.warning(self, "안내", f"이미 등록된 관심 종목입니다: {name} ({ticker})")
                    return
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(ticker))
            self.table.setItem(row, 1, QTableWidgetItem(name))
            self._adjust_columns()
            self.table.selectRow(row)

    def _add_row(self):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(""))
        self.table.setItem(row, 1, QTableWidgetItem(""))
        self.table.setCurrentCell(row, 0)
        self.table.editItem(self.table.item(row, 0))

    def _del_row(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "안내", "삭제할 관심 종목 행을 먼저 선택해주세요.")
            return
        self.table.removeRow(row)

    def _save_watchlist(self):
        new_watchlist: List[WatchlistConfig] = []
        seen = set()

        for row in range(self.table.rowCount()):
            ticker_item = self.table.item(row, 0)
            name_item = self.table.item(row, 1)

            ticker = ticker_item.text().strip() if ticker_item else ""
            name = name_item.text().strip() if name_item else ""

            if not ticker:
                QMessageBox.critical(self, "오류", f"종목코드는 빈 값일 수 없습니다 (행 {row + 1}).")
                return

            if ticker in seen:
                QMessageBox.critical(self, "오류", f"중복된 관심 종목코드입니다: {ticker}")
                return

            seen.add(ticker)
            new_watchlist.append(WatchlistConfig(ticker=ticker, name=name or ticker))

        self.config.watchlist = new_watchlist
        try:
            save_config(self.config)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "오류", f"관심 종목 저장 실패: {e}")


class MarketDataPage(QWidget):
    watchlist_updated = Signal()

    def __init__(self, market_service: MarketDataService, config: AppConfig, parent=None):
        super().__init__(parent)
        self.market_service = market_service
        self.config = config

        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(16)

        # 상단 필터 바
        filter_bar = QHBoxLayout()
        lbl_ticker = QLabel("ETF 종목 선택:")
        lbl_ticker.setStyleSheet("color: #94a3b8; font-weight: 500;")
        filter_bar.addWidget(lbl_ticker)

        self.combo_ticker = QComboBox()
        self.combo_ticker.setMinimumWidth(260)
        self.combo_ticker.currentIndexChanged.connect(self.refresh)
        filter_bar.addWidget(self.combo_ticker)

        filter_bar.addSpacing(16)

        lbl_period = QLabel("조회 기간:")
        lbl_period.setStyleSheet("color: #94a3b8; font-weight: 500;")
        filter_bar.addWidget(lbl_period)

        self.combo_period = QComboBox()
        self.combo_period.addItem("최근 3개월", "3m")
        self.combo_period.addItem("최근 6개월", "6m")
        self.combo_period.addItem("최근 1년", "1y")
        self.combo_period.addItem("전체 기간", "all")
        self.combo_period.currentIndexChanged.connect(self.refresh)
        filter_bar.addWidget(self.combo_period)

        filter_bar.addSpacing(16)

        # 관심종목 관리 버튼
        btn_watchlist = QPushButton("⭐ 관심종목 관리")
        btn_watchlist.setProperty("class", "secondary-btn")
        btn_watchlist.clicked.connect(self._open_watchlist_dialog)
        filter_bar.addWidget(btn_watchlist)

        filter_bar.addStretch()
        main_layout.addLayout(filter_bar)

        # 상단 가격 추이 차트 패널
        chart_frame = QFrame()
        chart_frame.setProperty("class", "card")
        chart_layout = QVBoxLayout(chart_frame)
        self.chart = PriceTrendChart()
        chart_layout.addWidget(self.chart)
        main_layout.addWidget(chart_frame)

        # 하단 일별 시세 테이블
        tbl_lbl = QLabel("일별 상세 가격 데이터 (차트에 마우스를 올리면 상세 시세 툴팁이 표시됩니다)")
        tbl_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #f8fafc;")
        main_layout.addWidget(tbl_lbl)

        self.table = QTableWidget()
        headers = ["일자", "종목코드", "시가", "고가", "저가", "종가", "NAV", "거래량", "거래대금"]
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

        self.update_etf_list(self.config)

    def _open_watchlist_dialog(self):
        dlg = WatchlistDialog(self.config, repo=self.market_service.repo, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self.config = load_config()
            self.update_etf_list(self.config)
            self.watchlist_updated.emit()
            QMessageBox.information(
                self,
                "관심 종목 반영 완료",
                "관심 종목이 저장되었습니다.\n\n새로 등록된 종목의 시세를 수집하려면 상단의 [🔄 시장 데이터 업데이트] 버튼을 눌러주세요.",
            )

    def refresh(self):
        ticker = self.combo_ticker.currentData()
        if not ticker:
            return
        period = self.combo_period.currentData()

        prices = self.market_service.get_history_by_range(ticker, period=period)
        high_p, _ = self.market_service.get_recent_3m_high(ticker)

        # 차트 갱신 (마우스 호버 툴팁용 상세 데이터 함께 전달)
        dates = [p.date for p in prices]
        close_prices = [p.close_price for p in prices]
        raw_text = self.combo_ticker.currentText()
        ticker_name = raw_text.split("] ")[-1].split(" (")[0] if "] " in raw_text else raw_text.split(" (")[0]

        details = [
            {
                "date": p.date,
                "open": p.open_price,
                "high": p.high_price,
                "low": p.low_price,
                "close": p.close_price,
                "volume": p.volume,
                "nav": p.nav,
            }
            for p in prices
        ]

        self.chart.plot(dates, close_prices, ticker_name=ticker_name, high_price=high_p, details=details)

        # 테이블 갱신 (최신순)
        self.table.setRowCount(len(prices))
        for row, p in enumerate(reversed(prices)):
            date_fmt = f"{p.date[:4]}-{p.date[4:6]}-{p.date[6:]}" if len(p.date) == 8 else p.date
            self.table.setItem(row, 0, QTableWidgetItem(date_fmt))
            self.table.setItem(row, 1, QTableWidgetItem(p.ticker))
            self.table.setItem(row, 2, QTableWidgetItem(f"{p.open_price:,.0f}원"))
            self.table.setItem(row, 3, QTableWidgetItem(f"{p.high_price:,.0f}원"))
            self.table.setItem(row, 4, QTableWidgetItem(f"{p.low_price:,.0f}원"))
            self.table.setItem(row, 5, QTableWidgetItem(f"{p.close_price:,.0f}원"))
            self.table.setItem(row, 6, QTableWidgetItem(f"{p.nav:,.2f}원" if p.nav else "-"))
            self.table.setItem(row, 7, QTableWidgetItem(f"{p.volume:,}"))
            self.table.setItem(row, 8, QTableWidgetItem(f"{p.trading_value:,.0f}원"))

        self.table.resizeColumnsToContents()
        for col in range(self.table.columnCount()):
            cur_w = self.table.columnWidth(col)
            self.table.setColumnWidth(col, cur_w + 6)

    def update_etf_list(self, config: AppConfig):
        """설정 변경 후 포트폴리오 종목 및 관심 종목 콤보박스 목록 갱신"""
        self.config = config
        current_ticker = self.combo_ticker.currentData()
        self.combo_ticker.blockSignals(True)
        self.combo_ticker.clear()

        # 1. 포트폴리오 종목
        for etf in self.config.etfs:
            self.combo_ticker.addItem(f"[포트폴리오] {etf.name} ({etf.ticker})", etf.ticker)

        # 2. 관심 종목 (포트폴리오와 겹치지 않는 종목)
        portfolio_tickers = {e.ticker for e in self.config.etfs}
        for w in getattr(self.config, "watchlist", []):
            if w.ticker not in portfolio_tickers:
                self.combo_ticker.addItem(f"[관심종목] {w.name} ({w.ticker})", w.ticker)

        # 기존 선택 종목 복원
        selected_idx = 0
        for idx in range(self.combo_ticker.count()):
            if self.combo_ticker.itemData(idx) == current_ticker:
                selected_idx = idx
                break

        self.combo_ticker.setCurrentIndex(selected_idx)
        self.combo_ticker.blockSignals(False)
        self.refresh()
