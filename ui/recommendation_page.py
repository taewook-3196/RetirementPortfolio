"""
ui/recommendation_page.py
매수 추천 및 자산 기준 리밸런싱 권장 화면.
- 모드 1: [💰 월간 신규 매수 추천] (월 1,000만원 기본매수 + 낙폭별 정액 추가매수)
- 모드 2: [🔄 자산 기준 리밸런싱 권장] (추가 자금 투입 없이 보유자산 기준: 낙폭 추가매수 & 5%이상 상승 시 익절)
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QLabel,
    QFrame,
    QTextEdit,
    QPushButton,
)
from PySide6.QtCore import Qt
from services.recommendation_service import RecommendationService


class RecommendationPage(QWidget):
    def __init__(self, recommendation_service: RecommendationService, parent=None):
        super().__init__(parent)
        self.rec_service = recommendation_service
        self._current_mode = "monthly"  # "monthly" or "rebalance"
        self._cached_monthly: List[Any] = []
        self._cached_rebalance: List[Any] = []
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(14)

        # 1. 상단 모드 전환 툴바
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        self.btn_mode_monthly = QPushButton("💰 월간 신규 매수 추천")
        self.btn_mode_monthly.setProperty("class", "primary-btn")
        self.btn_mode_monthly.clicked.connect(lambda: self._set_mode("monthly"))
        top_bar.addWidget(self.btn_mode_monthly)

        self.btn_mode_rebalance = QPushButton("🔄 자산 기준 리밸런싱 권장 (무추가입금)")
        self.btn_mode_rebalance.setProperty("class", "secondary-btn")
        self.btn_mode_rebalance.clicked.connect(lambda: self._set_mode("rebalance"))
        top_bar.addWidget(self.btn_mode_rebalance)

        top_bar.addStretch()
        main_layout.addLayout(top_bar)

        # 2. 안내 배너 카드
        self.info_frame = QFrame()
        self.info_frame.setProperty("class", "card")
        info_layout = QHBoxLayout(self.info_frame)
        info_layout.setContentsMargins(16, 12, 16, 12)
        self.info_lbl = QLabel()
        self.info_lbl.setWordWrap(True)
        self.info_lbl.setStyleSheet("font-size: 13px; color: #38bdf8;")
        info_layout.addWidget(self.info_lbl)
        main_layout.addWidget(self.info_frame)

        # 3. 요약 지표 카드
        self.summary_frame = QFrame()
        self.summary_frame.setProperty("class", "card")
        summary_layout = QHBoxLayout(self.summary_frame)
        summary_layout.setContentsMargins(16, 10, 16, 10)
        self.lbl_summary_1 = QLabel()
        self.lbl_summary_2 = QLabel()
        self.lbl_summary_3 = QLabel()
        self.lbl_summary_4 = QLabel()

        for lbl in (self.lbl_summary_1, self.lbl_summary_2, self.lbl_summary_3, self.lbl_summary_4):
            lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #f8fafc; margin-right: 18px;")
            summary_layout.addWidget(lbl)
        summary_layout.addStretch()
        main_layout.addWidget(self.summary_frame)

        # 4. 중앙 추천/리밸런싱 테이블
        self.table = QTableWidget()
        header = self.table.horizontalHeader()
        header.setSectionsMovable(True)
        header.setDragEnabled(True)
        header.setFirstSectionMovable(True)
        header.setSectionResizeMode(QHeaderView.Interactive)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        main_layout.addWidget(self.table)

        # 5. 하단 선택 종목 사유 상세 박스
        reason_box = QFrame()
        reason_box.setProperty("class", "card")
        reason_layout = QVBoxLayout(reason_box)
        reason_layout.setContentsMargins(16, 12, 16, 12)
        reason_lbl = QLabel("선택 종목 의사결정 사유 및 상세 배경")
        reason_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #f8fafc;")
        reason_layout.addWidget(reason_lbl)

        self.reason_text = QTextEdit()
        self.reason_text.setReadOnly(True)
        self.reason_text.setFixedHeight(75)
        self.reason_text.setStyleSheet(
            "background-color: #111827; border: 1px solid #1f2937; border-radius: 6px; color: #e2e8f0; font-size: 12px; padding: 6px;"
        )
        reason_layout.addWidget(self.reason_text)
        main_layout.addWidget(reason_box)

        self._update_banner()

    def _set_mode(self, mode: str):
        if self._current_mode == mode:
            return
        self._current_mode = mode
        if mode == "monthly":
            self.btn_mode_monthly.setProperty("class", "primary-btn")
            self.btn_mode_rebalance.setProperty("class", "secondary-btn")
        else:
            self.btn_mode_monthly.setProperty("class", "secondary-btn")
            self.btn_mode_rebalance.setProperty("class", "primary-btn")

        # 스타일 리프레시
        self.btn_mode_monthly.style().unpolish(self.btn_mode_monthly)
        self.btn_mode_monthly.style().polish(self.btn_mode_monthly)
        self.btn_mode_rebalance.style().unpolish(self.btn_mode_rebalance)
        self.btn_mode_rebalance.style().polish(self.btn_mode_rebalance)

        self._update_banner()
        self.refresh(account_id=getattr(self, "_current_account_id", None))

    def _update_banner(self):
        if self._current_mode == "monthly":
            self.info_lbl.setText(
                "💡 <b>월간 신규 매수 의사결정 모델</b>: 매월 유입되는 투자금(기본 1,000만원)을 목표비중 부족분과 "
                "최근 3개월 고점 대비 하락률에 따라 최적 배분합니다."
            )
        else:
            self.info_lbl.setText(
                "💡 <b>자산 기준 리밸런싱 모델 (무추가입금)</b>: 추가 매수 자금이 없을 때 현재 보유 자산을 기준으로 작동하며, "
                "최근 3개월 고점 대비 <b>낙폭(-5%~-20%↓) 시 10~30% 추가 매수</b>, <b>5% 이상 상승 시 절반(+5%p↑) 익절 매도</b>를 권장합니다."
            )

    def refresh(self, account_id: Optional[int] = None):
        self._current_account_id = account_id
        if self._current_mode == "monthly":
            self._render_monthly_recommendations()
        else:
            self._render_rebalancing_recommendations()

    def _render_monthly_recommendations(self):
        rec_data = self.rec_service.calculate_recommendations(account_id=getattr(self, "_current_account_id", None), auto_save=True)
        self._cached_monthly = rec_data.get("recommendations", [])
        summary = rec_data.get("summary", {})

        # 요약 표시
        b_base = summary.get("base_monthly_budget", 0)
        b_add = summary.get("total_additional_buy", 0)
        b_tot = summary.get("total_recommended_buy", 0)
        b_rem = summary.get("remaining_cash", 0)
        is_invested = summary.get("already_invested_in_cycle", False)
        cycle_desc = summary.get("cycle_desc", "")

        self.lbl_summary_1.setText(f"기본 매수: {b_base:,.0f}원")
        if is_invested:
            self.lbl_summary_2.setText("추가 매수: 0원 (납입완료)")
            self.info_lbl.setText(
                f"💡 <b>투자 주기 납입 완료 안내</b>: {cycle_desc}에 이미 매수(납입) 이력이 확인되어 "
                "이번 주기에는 추가 매수 금액이 추천되지 않습니다 (추가 매수 0원)."
            )
        else:
            self.lbl_summary_2.setText(f"추가 매수: {b_add:,.0f}원")
            self._update_banner()

        self.lbl_summary_3.setText(f"총 추천 매수: {b_tot:,.0f}원")
        self.lbl_summary_4.setText(f"남은 투자 한도: {b_rem:,.0f}원")

        headers = [
            "종목코드", "종목명", "목표비중", "현재비중", "비중차이",
            "3개월 고점", "현재가", "Drawdown", "DD점수", "WG점수", "우선순위",
            "기본매수", "추가매수", "총 추천매수", "매수후 예상비중"
        ]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        self.table.setRowCount(len(self._cached_monthly))
        for row, r in enumerate(self._cached_monthly):
            self.table.setItem(row, 0, QTableWidgetItem(r.ticker))
            self.table.setItem(row, 1, QTableWidgetItem(r.name))
            self.table.setItem(row, 2, QTableWidgetItem(f"{r.target_weight * 100:.1f}%"))
            self.table.setItem(row, 3, QTableWidgetItem(f"{r.current_weight * 100:.1f}%"))

            # 비중차이: 목표 대비 현재비중 괴리 (현재비중 - 목표비중)
            weight_diff = r.current_weight - r.target_weight
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

            self.table.setItem(row, 5, QTableWidgetItem(f"{r.recent_high:,.0f}원"))
            self.table.setItem(row, 6, QTableWidgetItem(f"{r.current_price:,.0f}원"))

            dd_item = QTableWidgetItem(f"{r.drawdown * 100:.2f}%")
            if r.drawdown <= -0.05:
                dd_item.setForeground(Qt.red)
            self.table.setItem(row, 7, dd_item)

            self.table.setItem(row, 8, QTableWidgetItem(str(r.drawdown_score)))
            self.table.setItem(row, 9, QTableWidgetItem(f"{r.weight_gap_score:.2f}"))

            p_item = QTableWidgetItem(f"{r.priority_score:.2f}")
            p_item.setForeground(Qt.cyan)
            self.table.setItem(row, 10, p_item)

            self.table.setItem(row, 11, QTableWidgetItem(f"{r.base_buy:,.0f}원"))
            self.table.setItem(row, 12, QTableWidgetItem(f"{r.additional_buy:,.0f}원"))

            buy_item = QTableWidgetItem(f"{r.recommended_buy:,.0f}원")
            buy_item.setForeground(Qt.cyan)
            self.table.setItem(row, 13, buy_item)

            self.table.setItem(row, 14, QTableWidgetItem(f"{r.expected_weight_after * 100:.1f}%"))

        self.table.resizeColumnsToContents()
        for col in range(self.table.columnCount()):
            cur_w = self.table.columnWidth(col)
            if col == 1:
                self.table.setColumnWidth(col, cur_w + 10)
            else:
                self.table.setColumnWidth(col, cur_w + 6)

        if self._cached_monthly:
            self.table.selectRow(0)
            self._on_row_selected()

    def _render_rebalancing_recommendations(self):
        reb_data = self.rec_service.calculate_rebalancing(account_id=getattr(self, "_current_account_id", None))
        self._cached_rebalance = reb_data.get("recommendations", [])
        summary = reb_data.get("summary", {})

        # 요약 지표 갱신
        tot_val = summary.get("total_portfolio_value", 0.0)
        tot_sell = summary.get("total_sell_amount", 0)
        tot_buy = summary.get("total_buy_amount", 0)
        net_flow = summary.get("net_cash_flow", 0)

        self.lbl_summary_1.setText(f"총 보유자산: {tot_val:,.0f}원")
        self.lbl_summary_2.setText(f"익절 매도(예정): {tot_sell:,.0f}원")
        self.lbl_summary_3.setText(f"추가 매수(예정): {tot_buy:,.0f}원")

        flow_prefix = "+" if net_flow > 0 else ""
        self.lbl_summary_4.setText(f"순 현금변동: {flow_prefix}{net_flow:,.0f}원")
        if net_flow > 0:
            self.lbl_summary_4.setStyleSheet("font-size: 13px; font-weight: bold; color: #34d399;")
        elif net_flow < 0:
            self.lbl_summary_4.setStyleSheet("font-size: 13px; font-weight: bold; color: #f87171;")
        else:
            self.lbl_summary_4.setStyleSheet("font-size: 13px; font-weight: 600; color: #94a3b8;")

        headers = [
            "종목코드", "종목명", "목표비중", "현재비중", "현재가",
            "3개월 기준고점", "고점대비 등락률", "리밸런싱 권장행동", "권장 금액", "권장 수량", "사후 예상비중"
        ]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        self.table.setRowCount(len(self._cached_rebalance))
        for row, r in enumerate(self._cached_rebalance):
            self.table.setItem(row, 0, QTableWidgetItem(r.ticker))
            self.table.setItem(row, 1, QTableWidgetItem(r.name))
            self.table.setItem(row, 2, QTableWidgetItem(f"{r.target_weight * 100:.1f}%"))
            self.table.setItem(row, 3, QTableWidgetItem(f"{r.current_weight * 100:.1f}%"))
            self.table.setItem(row, 4, QTableWidgetItem(f"{r.current_price:,.0f}원"))
            self.table.setItem(row, 5, QTableWidgetItem(f"{r.reference_high:,.0f}원"))

            # 등락률
            chg_item = QTableWidgetItem(f"{r.price_change_pct * 100:+.2f}%")
            if r.price_change_pct > 0.05:
                chg_item.setForeground(Qt.green)
            elif r.price_change_pct <= -0.05:
                chg_item.setForeground(Qt.red)
            self.table.setItem(row, 6, chg_item)

            # 리밸런싱 행동
            act_item = QTableWidgetItem(r.action_label)
            if r.action == "SELL":
                act_item.setForeground(Qt.green)
            elif r.action == "BUY":
                act_item.setForeground(Qt.yellow)
            self.table.setItem(row, 7, act_item)

            # 권장 금액
            if r.action == "SELL":
                amt_str = f"-{r.recommended_amount:,.0f}원"
                amt_item = QTableWidgetItem(amt_str)
                amt_item.setForeground(Qt.green)
            elif r.action == "BUY":
                amt_str = f"+{r.recommended_amount:,.0f}원"
                amt_item = QTableWidgetItem(amt_str)
                amt_item.setForeground(Qt.yellow)
            else:
                amt_item = QTableWidgetItem("0원 (유지)")
            self.table.setItem(row, 8, amt_item)

            # 권장 수량
            if r.recommended_shares > 0:
                prefix = "-" if r.action == "SELL" else "+"
                shares_str = f"{prefix}{r.recommended_shares:,}주"
            else:
                shares_str = "0주"
            self.table.setItem(row, 9, QTableWidgetItem(shares_str))

            # 사후 예상 비중
            self.table.setItem(row, 10, QTableWidgetItem(f"{r.expected_weight_after * 100:.1f}%"))

        self.table.resizeColumnsToContents()
        for col in range(self.table.columnCount()):
            cur_w = self.table.columnWidth(col)
            if col == 1:
                self.table.setColumnWidth(col, cur_w + 10)
            else:
                self.table.setColumnWidth(col, cur_w + 6)

        if self._cached_rebalance:
            self.table.selectRow(0)
            self._on_row_selected()

    def _on_row_selected(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return
        row = selected_rows[0].row()

        if self._current_mode == "monthly":
            if 0 <= row < len(self._cached_monthly):
                r = self._cached_monthly[row]
                self.reason_text.setHtml(
                    f"<b style='color:#38bdf8;'>[{r.name} ({r.ticker})] - 월간 매수 추천 사유</b><br/>"
                    f"{r.reason}"
                )
        else:
            if 0 <= row < len(self._cached_rebalance):
                r = self._cached_rebalance[row]
                action_color = "#34d399" if r.action == "SELL" else ("#fbbf24" if r.action == "BUY" else "#94a3b8")
                self.reason_text.setHtml(
                    f"<b style='color:#38bdf8;'>[{r.name} ({r.ticker})] - 자산 리밸런싱 권장 ({r.action_label})</b><br/>"
                    f"<span style='color:{action_color};'>• {r.reason}</span>"
                )
