"""
ui/dashboard_page.py
대시보드 화면 (프롬프트 44번, 45번 항목).
- 상단: 6대 핵심 KPI 요약 카드
- 중앙: 이번 달 투자 계획 (기본매수, 추가매수, 총 추천매수)
- 하단: ETF 포트폴리오 및 매수 추천 현황 테이블
"""

from __future__ import annotations
from typing import Dict, Any, Optional, List
from core.config import ETFConfig
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QLabel,
    QFrame,
)
from PySide6.QtCore import Qt
from ui.widgets.summary_card import SummaryCard
from services.portfolio_service import PortfolioService
from services.recommendation_service import RecommendationService


class DashboardPage(QWidget):
    def __init__(
        self,
        portfolio_service: PortfolioService,
        recommendation_service: RecommendationService,
        parent=None,
    ):
        super().__init__(parent)
        self.portfolio_service = portfolio_service
        self.rec_service = recommendation_service

        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(20)

        # 1. 상단 6대 KPI 요약 카드 그리드
        cards_grid = QGridLayout()
        cards_grid.setSpacing(14)

        self.card_invested = SummaryCard("총 투자원금", "0원")
        self.card_current_val = SummaryCard("현재 평가금액", "0원")
        self.card_pnl = SummaryCard("총 손익", "0원", badge="0.0%", badge_type="neutral")
        self.card_roi = SummaryCard("총 수익률", "0.0%")
        self.card_dividends = SummaryCard("누적 분배금", "0원")
        self.card_remaining_cash = SummaryCard("남은 투자금 한도", "0원", badge_type="accent")

        cards_grid.addWidget(self.card_invested, 0, 0)
        cards_grid.addWidget(self.card_current_val, 0, 1)
        cards_grid.addWidget(self.card_pnl, 0, 2)
        cards_grid.addWidget(self.card_roi, 1, 0)
        cards_grid.addWidget(self.card_dividends, 1, 1)
        cards_grid.addWidget(self.card_remaining_cash, 1, 2)

        main_layout.addLayout(cards_grid)

        # 2. 중앙 이번 달 투자 계획 카드
        plan_frame = QFrame()
        plan_frame.setProperty("class", "card")
        plan_layout = QHBoxLayout(plan_frame)
        plan_layout.setContentsMargins(20, 16, 20, 16)

        plan_title_box = QVBoxLayout()
        plan_title_row = QHBoxLayout()
        self.plan_title = QLabel("이번 달 투자 계획")
        self.plan_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #f8fafc;")
        self.badge_cycle = QLabel("매월 25일")
        self.badge_cycle.setObjectName("CycleBadge")
        plan_title_row.addWidget(self.plan_title)
        plan_title_row.addWidget(self.badge_cycle)
        plan_title_row.addStretch()

        self.plan_sub = QLabel("월간 기본 매수 및 낙폭에 따른 전략적 추가매수")
        self.plan_sub.setStyleSheet("font-size: 11px; color: #94a3b8;")
        plan_title_box.addLayout(plan_title_row)
        plan_title_box.addWidget(self.plan_sub)
        plan_layout.addLayout(plan_title_box)

        plan_layout.addStretch()

        self.lbl_base_buy = QLabel("기본매수: 0원")
        self.lbl_base_buy.setStyleSheet("font-size: 14px; font-weight: 600; color: #e2e8f0; margin-right: 20px;")
        plan_layout.addWidget(self.lbl_base_buy)

        self.lbl_add_buy = QLabel("추가매수: 0원")
        self.lbl_add_buy.setStyleSheet("font-size: 14px; font-weight: 600; color: #f59e0b; margin-right: 20px;")
        plan_layout.addWidget(self.lbl_add_buy)

        self.lbl_total_buy = QLabel("총 추천매수: 0원")
        self.lbl_total_buy.setStyleSheet("font-size: 17px; font-weight: bold; color: #38bdf8;")
        plan_layout.addWidget(self.lbl_total_buy)

        main_layout.addWidget(plan_frame)

        # 3. 하단 ETF 현황 테이블
        table_header = QLabel("ETF 포트폴리오 현황 및 매수 추천")
        table_header.setStyleSheet("font-size: 14px; font-weight: bold; color: #f8fafc;")
        main_layout.addWidget(table_header)

        self.table = QTableWidget()
        headers = [
            "종목코드", "종목명", "목표비중", "현재비중", "비중차이",
            "현재가", "3개월 고점", "Drawdown", "평가수익률", "추천 매수금"
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
        """데이터를 최신화하여 화면에 반영합니다."""
        from strategy.cycle_helper import calculate_next_investment_date

        positions = self.portfolio_service.get_positions(account_id=account_id)
        summary = self.portfolio_service.get_summary(positions, account_id=account_id)
        rec_data = self.rec_service.calculate_recommendations(account_id=account_id, auto_save=True)
        rec_summary = rec_data.get("summary", {})
        recs = rec_data.get("recommendations", [])
        recs_map = {r.ticker: r for r in recs}

        # 계좌 및 주기 정보 반영
        is_invested = rec_summary.get("already_invested_in_cycle", False)
        if account_id is not None:
            acc = self.portfolio_service.repo.get_account(account_id)
            if acc:
                ctype = getattr(acc, "buy_cycle_type", "monthly")
                cdetail = getattr(acc, "buy_cycle_detail", "25")
                _, _, cycle_text = calculate_next_investment_date(ctype, cdetail)
                self.plan_title.setText(f"{acc.account_name} 투자 계획")
                if is_invested:
                    self.badge_cycle.setText(f"{cycle_text}  ·  ✅ 이번 주기 납입완료")
                    self.badge_cycle.setStyleSheet(
                        "background-color: rgba(16, 185, 129, 0.15); color: #34d399; "
                        "border: 1px solid rgba(16, 185, 129, 0.35); border-radius: 4px; padding: 2px 8px; font-weight: bold; font-size: 11px;"
                    )
                else:
                    self.badge_cycle.setText(cycle_text)
                    self.badge_cycle.setStyleSheet(
                        "background-color: rgba(59, 130, 246, 0.2); color: #60a5fa; "
                        "border: 1px solid rgba(59, 130, 246, 0.4); border-radius: 4px; padding: 2px 8px; font-weight: bold; font-size: 11px;"
                    )
                self.badge_cycle.setVisible(True)
                self.plan_sub.setText(f"계좌: {acc.broker or '증권사'} {acc.account_number or ''} | 한도: {acc.initial_capital:,.0f}원")
            else:
                self.plan_title.setText("이번 주기 투자 계획")
                self.badge_cycle.setVisible(False)
        else:
            self.plan_title.setText("전체 통합 투자 계획")
            if is_invested:
                self.badge_cycle.setText("🌐 전체 계좌 통합  ·  ✅ 납입 이력 확인")
                self.badge_cycle.setStyleSheet(
                    "background-color: rgba(16, 185, 129, 0.15); color: #34d399; "
                    "border: 1px solid rgba(16, 185, 129, 0.35); border-radius: 4px; padding: 2px 8px; font-weight: bold; font-size: 11px;"
                )
            else:
                self.badge_cycle.setText("🌐 전체 계좌 통합")
                self.badge_cycle.setStyleSheet(
                    "background-color: rgba(59, 130, 246, 0.2); color: #60a5fa; "
                    "border: 1px solid rgba(59, 130, 246, 0.4); border-radius: 4px; padding: 2px 8px; font-weight: bold; font-size: 11px;"
                )
            self.badge_cycle.setVisible(True)
            self.plan_sub.setText("등록된 모든 계좌의 합산 자산 및 종합 매수 계획")

        # 1. 상단 KPI 카드 업데이트
        self.card_invested.set_value(f"{summary.total_invested:,.0f}원")
        self.card_current_val.set_value(f"{summary.total_current_value:,.0f}원")

        pnl_badge_type = "positive" if summary.total_pnl > 0 else ("negative" if summary.total_pnl < 0 else "neutral")
        pnl_prefix = "+" if summary.total_pnl > 0 else ""
        self.card_pnl.set_value(f"{pnl_prefix}{summary.total_pnl:,.0f}원")
        self.card_pnl.set_badge(f"{pnl_prefix}{summary.total_roi * 100:.2f}%", pnl_badge_type)

        self.card_roi.set_value(f"{pnl_prefix}{summary.total_roi * 100:.2f}%")
        self.card_dividends.set_value(f"{summary.total_dividends:,.0f}원")
        self.card_remaining_cash.set_value(f"{summary.remaining_cash:,.0f}원")

        # 2. 투자 계획 업데이트
        base_b = rec_summary.get("base_monthly_budget", 0)
        add_b = rec_summary.get("total_additional_buy", 0)
        tot_b = rec_summary.get("total_recommended_buy", 0)
        self.lbl_base_buy.setText(f"기본매수: {base_b:,.0f}원")
        if is_invested:
            self.lbl_add_buy.setText("추가매수: 0원 (납입완료)")
        else:
            self.lbl_add_buy.setText(f"추가매수: {add_b:,.0f}원")
        self.lbl_total_buy.setText(f"총 추천매수: {tot_b:,.0f}원")

        # 3. 테이블 업데이트
        target_etfs = self.portfolio_service.get_target_etfs(account_id)
        target_tickers = {e.ticker for e in target_etfs}
        extra_items: List[ETFConfig] = []
        for ticker, pos in positions.items():
            if ticker not in target_tickers and (pos.quantity > 0 or pos.total_buy_cost > 0):
                extra_items.append(ETFConfig(ticker=ticker, name=pos.name or ticker, target_weight=0.0))
        display_etfs = target_etfs + extra_items

        self.table.setRowCount(len(display_etfs))
        for row, etf in enumerate(display_etfs):
            pos = positions.get(etf.ticker)
            rec = recs_map.get(etf.ticker)

            cur_price = pos.current_price if pos else 0.0
            cur_weight = (pos.current_value / summary.total_current_value) if summary.total_current_value > 0 and pos else 0.0
            # 비중차이: 목표 대비 현재비중 괴리 (현재비중 - 목표비중)
            # 목표보다 많으면 +, 목표보다 모자라면 -
            weight_diff = cur_weight - etf.target_weight
            roi = pos.unrealized_roi if pos else 0.0

            high_p = rec.recent_high if rec else cur_price
            dd = rec.drawdown if rec else 0.0
            rec_buy = rec.recommended_buy if rec else 0

            self.table.setItem(row, 0, QTableWidgetItem(etf.ticker))
            self.table.setItem(row, 1, QTableWidgetItem(etf.name))
            self.table.setItem(row, 2, QTableWidgetItem(f"{etf.target_weight * 100:.1f}%"))
            self.table.setItem(row, 3, QTableWidgetItem(f"{cur_weight * 100:.1f}%"))

            diff_pct = round(weight_diff * 100, 1)
            if abs(diff_pct) == 0.0:
                diff_pct = 0.0
            
            diff_str = f"{diff_pct:+.1f}%p" if diff_pct != 0.0 else "0.0%p"
            gap_item = QTableWidgetItem(diff_str)
            if diff_pct > 0:
                gap_item.setForeground(Qt.green)
            elif diff_pct < 0:
                gap_item.setForeground(Qt.red)
            self.table.setItem(row, 4, gap_item)

            self.table.setItem(row, 5, QTableWidgetItem(f"{cur_price:,.0f}원"))
            self.table.setItem(row, 6, QTableWidgetItem(f"{high_p:,.0f}원"))

            dd_item = QTableWidgetItem(f"{dd * 100:.2f}%")
            if dd <= -0.05:
                dd_item.setForeground(Qt.red)
            self.table.setItem(row, 7, dd_item)

            roi_item = QTableWidgetItem(f"{roi * 100:+.2f}%")
            if roi > 0:
                roi_item.setForeground(Qt.green)
            elif roi < 0:
                roi_item.setForeground(Qt.red)
            self.table.setItem(row, 8, roi_item)

            buy_item = QTableWidgetItem(f"{rec_buy:,.0f}원")
            buy_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 9, buy_item)

        self.table.resizeColumnsToContents()
        for col in range(self.table.columnCount()):
            cur_w = self.table.columnWidth(col)
            if col == 1:  # 종목명
                self.table.setColumnWidth(col, cur_w + 10)
            else:
                self.table.setColumnWidth(col, cur_w + 6)
