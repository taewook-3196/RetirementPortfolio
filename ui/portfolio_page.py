"""
ui/portfolio_page.py
포트폴리오 상세 및 비중 비교 화면 (프롬프트 41번, 52번 항목).
- ETF별 상세 보유현황 및 손익 테이블
- 목표비중 vs 현재비중 도넛 차트
"""

from __future__ import annotations
from typing import Optional, List
from core.config import ETFConfig
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QLabel,
    QFrame,
)
from PySide6.QtCore import Qt
from ui.widgets.charts import AllocationDonutChart
from services.portfolio_service import PortfolioService


class PortfolioPage(QWidget):
    def __init__(self, portfolio_service: PortfolioService, parent=None):
        super().__init__(parent)
        self.portfolio_service = portfolio_service
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(20)

        # 1. 상단 비중 차트 패널
        chart_frame = QFrame()
        chart_frame.setProperty("class", "card")
        chart_layout = QVBoxLayout(chart_frame)
        chart_title = QLabel("포트폴리오 자산 배분 비중 비교")
        chart_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #f8fafc;")
        chart_layout.addWidget(chart_title)

        self.chart = AllocationDonutChart()
        chart_layout.addWidget(self.chart)
        main_layout.addWidget(chart_frame)

        # 2. 하단 상세 보유 테이블
        tbl_title = QLabel("보유 종목별 상세 손익 현황")
        tbl_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #f8fafc;")
        main_layout.addWidget(tbl_title)

        self.table = QTableWidget()
        headers = [
            "종목코드", "종목명", "보유수량", "평균매수가", "현재가",
            "총 매수금", "현재 평가금", "평가손익", "평가수익률", "실현손익", "누적분배금", "총손익"
        ]
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
        positions = self.portfolio_service.get_positions(account_id=account_id)
        summary = self.portfolio_service.get_summary(positions, account_id=account_id)

        target_etfs = self.portfolio_service.get_target_etfs(account_id=account_id)
        target_tickers = {e.ticker for e in target_etfs}

        extra_items: List[ETFConfig] = []
        for ticker, pos in positions.items():
            if ticker not in target_tickers and (pos.quantity > 0 or pos.total_buy_cost > 0):
                extra_items.append(ETFConfig(ticker=ticker, name=pos.name or ticker, target_weight=0.0))
        display_etfs = target_etfs + extra_items

        # 차트 갱신 (목표 비중 100% 미만 시 잔여분은 현금으로 차트에 반영)
        target_map = {e.name: e.target_weight for e in target_etfs}
        target_sum = sum(target_map.values())
        if target_sum < 0.999:
            target_map["현금"] = max(0.0, 1.0 - target_sum)

        current_map = {}
        total_assets = summary.total_current_value + summary.remaining_cash
        if total_assets > 0:
            for e in display_etfs:
                pos = positions.get(e.ticker)
                val = pos.current_value if pos else 0.0
                current_map[e.name] = val / total_assets
            if "현금" in target_map:
                current_map["현금"] = summary.remaining_cash / total_assets
        else:
            for e in display_etfs:
                current_map[e.name] = 0.0
            if "현금" in target_map:
                current_map["현금"] = 0.0

        self.chart.plot(target_map, current_map)

        # 테이블 갱신
        self.table.setRowCount(len(display_etfs))
        for row, etf in enumerate(display_etfs):
            pos = positions.get(etf.ticker)
            qty = pos.quantity if pos else 0
            avg_p = pos.average_buy_price if pos else 0.0
            cur_p = pos.current_price if pos else 0.0
            tot_cost = pos.total_buy_cost if pos else 0.0
            cur_val = pos.current_value if pos else 0.0
            unreal_pnl = pos.unrealized_pnl if pos else 0.0
            unreal_roi = pos.unrealized_roi if pos else 0.0
            real_pnl = pos.realized_pnl if pos else 0.0
            divs = pos.total_dividends if pos else 0.0
            tot_pnl = pos.total_pnl if pos else 0.0

            self.table.setItem(row, 0, QTableWidgetItem(etf.ticker))
            self.table.setItem(row, 1, QTableWidgetItem(etf.name))
            self.table.setItem(row, 2, QTableWidgetItem(f"{qty:,}주"))
            self.table.setItem(row, 3, QTableWidgetItem(f"{avg_p:,.0f}원"))
            self.table.setItem(row, 4, QTableWidgetItem(f"{cur_p:,.0f}원"))
            self.table.setItem(row, 5, QTableWidgetItem(f"{tot_cost:,.0f}원"))
            self.table.setItem(row, 6, QTableWidgetItem(f"{cur_val:,.0f}원"))

            pnl_item = QTableWidgetItem(f"{unreal_pnl:+,.0f}원")
            if unreal_pnl > 0:
                pnl_item.setForeground(Qt.green)
            elif unreal_pnl < 0:
                pnl_item.setForeground(Qt.red)
            self.table.setItem(row, 7, pnl_item)

            roi_item = QTableWidgetItem(f"{unreal_roi * 100:+.2f}%")
            if unreal_roi > 0:
                roi_item.setForeground(Qt.green)
            elif unreal_roi < 0:
                roi_item.setForeground(Qt.red)
            self.table.setItem(row, 8, roi_item)

            self.table.setItem(row, 9, QTableWidgetItem(f"{real_pnl:+,.0f}원"))
            self.table.setItem(row, 10, QTableWidgetItem(f"{divs:,.0f}원"))

            tot_pnl_item = QTableWidgetItem(f"{tot_pnl:+,.0f}원")
            if tot_pnl > 0:
                tot_pnl_item.setForeground(Qt.green)
            elif tot_pnl < 0:
                tot_pnl_item.setForeground(Qt.red)
            self.table.setItem(row, 11, tot_pnl_item)

        self.table.resizeColumnsToContents()
        for col in range(self.table.columnCount()):
            cur_w = self.table.columnWidth(col)
            if col == 1:  # 종목명
                self.table.setColumnWidth(col, cur_w + 10)
            else:
                self.table.setColumnWidth(col, cur_w + 6)
