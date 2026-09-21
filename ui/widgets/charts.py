"""
ui/widgets/charts.py
Matplotlib 기반의 PySide6 내장 인터랙티브 차트 위젯 (프롬프트 52번 항목).
- 목표비중 vs 현재비중 비교 도넛/막대 차트
- 최근 가격 추이 라인 차트
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional
from PySide6.QtWidgets import QWidget, QVBoxLayout, QToolTip
from PySide6.QtGui import QCursor
from PySide6.QtCore import QPoint
import matplotlib
matplotlib.use("QtAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


# 한글 폰트 설정 (Windows 맑은 고딕 기본 적용)
plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False


class AllocationDonutChart(QWidget):
    """목표비중 vs 현재비중 도넛 차트 위젯"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 다크 테마 Figure
        self.figure = Figure(figsize=(5, 3.2), facecolor="#182232")
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)

    def plot(self, target_weights: Dict[str, float], current_weights: Dict[str, float]):
        self.figure.clear()
        if not target_weights:
            self.canvas.draw()
            return

        ax1 = self.figure.add_subplot(1, 2, 1)
        ax2 = self.figure.add_subplot(1, 2, 2)

        palette = ["#3b82f6", "#10b981", "#f59e0b", "#ec4899", "#8b5cf6", "#06b6d4", "#f97316", "#84cc16", "#a855f7"]
        cash_color = "#64748b"

        # 1. 목표비중
        labels1 = list(target_weights.keys())
        sizes1 = [max(v, 0.0) for v in target_weights.values()]
        colors1 = [cash_color if lbl == "현금" else palette[i % len(palette)] for i, lbl in enumerate(labels1)]
        ax1.pie(
            sizes1,
            labels=labels1,
            autopct="%1.0f%%",
            startangle=90,
            colors=colors1,
            textprops={"color": "#e2e8f0", "fontsize": 9},
            wedgeprops={"edgecolor": "#182232", "linewidth": 2, "width": 0.45},
        )
        ax1.set_title("목표 비중", color="#94a3b8", fontsize=11, fontweight="bold")

        # 2. 현재비중
        labels2 = list(current_weights.keys())
        sizes2 = [max(v, 0.0) for v in current_weights.values()]
        colors2 = [cash_color if lbl == "현금" else palette[i % len(palette)] for i, lbl in enumerate(labels2)]
        if sum(sizes2) <= 0:
            sizes2 = [1] * len(labels2)
            autopct_fn = lambda p: "0%"
        else:
            autopct_fn = "%1.0f%%"

        ax2.pie(
            sizes2,
            labels=labels2,
            autopct=autopct_fn,
            startangle=90,
            colors=colors2,
            textprops={"color": "#e2e8f0", "fontsize": 9},
            wedgeprops={"edgecolor": "#182232", "linewidth": 2, "width": 0.45},
        )
        ax2.set_title("현재 비중", color="#94a3b8", fontsize=11, fontweight="bold")

        self.figure.subplots_adjust(left=0.05, right=0.95, top=0.88, bottom=0.05, wspace=0.3)
        self.canvas.draw()


class PriceTrendChart(QWidget):
    """ETF 가격 추이 라인 차트 위젯 (마우스 호버 툴팁 및 커서 가이드선 지원)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.figure = Figure(figsize=(6, 3.2), facecolor="#182232")
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)

        self._details: List[Optional[Dict[str, Any]]] = []
        self._valid_dates: List[str] = []
        self._valid_prices: List[float] = []
        self._ticker_name: str = ""
        self._ax = None
        self._cursor_line = None
        self._highlight_dot = None

        self.canvas.mpl_connect("motion_notify_event", self._on_mouse_move)
        self.canvas.mpl_connect("figure_leave_event", self._on_figure_leave)

    def plot(
        self,
        dates: List[str],
        prices: List[float],
        ticker_name: str,
        high_price: Optional[float] = None,
        details: Optional[List[Dict[str, Any]]] = None,
    ):
        self.figure.clear()
        self._details = []
        self._valid_dates = []
        self._valid_prices = []
        self._ticker_name = ticker_name
        self._cursor_line = None
        self._highlight_dot = None
        self._ax = None

        if not dates or not prices:
            self.canvas.draw()
            return

        # 미거래일(0원 이하) 필터링
        raw_details = details or []
        valid_items = []
        for i, (d, p) in enumerate(zip(dates, prices)):
            if p > 0:
                det = raw_details[i] if i < len(raw_details) else None
                valid_items.append((d, p, det))

        if not valid_items:
            self.canvas.draw()
            return

        self._valid_dates = [item[0] for item in valid_items]
        self._valid_prices = [item[1] for item in valid_items]
        self._details = [item[2] for item in valid_items]

        ax = self.figure.add_subplot(1, 1, 1)
        ax.set_facecolor("#141c28")
        self._ax = ax

        # 날짜 포맷팅 (MM/DD)
        formatted_dates = [f"{d[4:6]}/{d[6:8]}" if len(d) == 8 else d for d in self._valid_dates]

        # 종가 라인 플롯
        ax.plot(formatted_dates, self._valid_prices, color="#38bdf8", linewidth=2.2, label=f"{ticker_name} 종가")

        # 3개월 고점 수평 기준선
        if high_price and high_price > 0:
            ax.axhline(
                y=high_price,
                color="#ef4444",
                linestyle="--",
                linewidth=1.5,
                label=f"3개월 고점 ({high_price:,.0f}원)",
            )

        # X축 눈금 간격 조절
        step = max(1, len(formatted_dates) // 6)
        ax.set_xticks(range(0, len(formatted_dates), step))
        ax.set_xticklabels([formatted_dates[i] for i in range(0, len(formatted_dates), step)], rotation=0)

        ax.tick_params(colors="#e2e8f0", labelsize=9.5)
        ax.grid(True, linestyle=":", alpha=0.35, color="#334155")
        for spine in ax.spines.values():
            spine.set_color("#334155")

        ax.legend(facecolor="#0f172a", edgecolor="#38bdf8", labelcolor="#f8fafc", fontsize=9.5)

        # 수직 점선 커서선 및 강조 마커 생성
        self._cursor_line = ax.axvline(x=0, color="#38bdf8", linestyle="--", linewidth=1.0, alpha=0.8, visible=False)
        (self._highlight_dot,) = ax.plot(
            [0], [0], "o", color="#38bdf8", markersize=7, visible=False, markeredgecolor="#ffffff", markeredgewidth=1.5
        )

        self.figure.tight_layout()
        self.canvas.draw()

    def _on_mouse_move(self, event):
        if self._ax is None or event.inaxes != self._ax or not self._valid_dates or event.xdata is None:
            self._hide_tooltip()
            return

        x_idx = int(round(event.xdata))
        if x_idx < 0 or x_idx >= len(self._valid_dates):
            self._hide_tooltip()
            return

        # 커서선 및 하이라이트 점 위치 갱신
        if self._cursor_line and self._highlight_dot:
            self._cursor_line.set_xdata([x_idx, x_idx])
            self._cursor_line.set_visible(True)
            self._highlight_dot.set_data([x_idx], [self._valid_prices[x_idx]])
            self._highlight_dot.set_visible(True)
            self.canvas.draw_idle()

        # 툴팁 HTML 내용 생성 (고대비 선명한 색상 적용)
        raw_date = self._valid_dates[x_idx]
        date_str = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}" if len(raw_date) == 8 else raw_date
        close_p = self._valid_prices[x_idx]
        detail = self._details[x_idx] if x_idx < len(self._details) else None

        if detail:
            o = detail.get("open", 0)
            h = detail.get("high", 0)
            l = detail.get("low", 0)
            v = detail.get("volume", 0)
            nav = detail.get("nav", 0)
            nav_txt = f"<br><span style='color:#94a3b8;'>• NAV:</span> <span style='color:#34d399; font-weight:bold;'>{nav:,.2f}원</span>" if nav else ""
            lines = (
                f"<div style='font-family: Pretendard, Malgun Gothic, sans-serif; font-size:12px; line-height:1.5; color:#f8fafc;'>"
                f"<div style='font-size:13px; font-weight:bold; color:#ffffff;'>📅 {date_str} [{self._ticker_name}]</div>"
                f"<hr style='border:0; border-top:1px solid #334155; margin:4px 0;'>"
                f"<span style='color:#94a3b8;'>• 종가:</span> <span style='color:#38bdf8; font-weight:bold; font-size:13px;'>{close_p:,.0f}원</span><br>"
                f"<span style='color:#94a3b8;'>• 시가:</span> <span style='color:#e2e8f0; font-weight:bold;'>{o:,.0f}원</span> | "
                f"<span style='color:#94a3b8;'>고가:</span> <span style='color:#f87171; font-weight:bold;'>{h:,.0f}원</span> | "
                f"<span style='color:#94a3b8;'>저가:</span> <span style='color:#60a5fa; font-weight:bold;'>{l:,.0f}원</span><br>"
                f"<span style='color:#94a3b8;'>• 거래량:</span> <span style='color:#fbbf24; font-weight:bold;'>{v:,}주</span>{nav_txt}"
                f"</div>"
            )
        else:
            lines = (
                f"<div style='font-family: Pretendard, Malgun Gothic, sans-serif; font-size:12px; line-height:1.5; color:#f8fafc;'>"
                f"<div style='font-size:13px; font-weight:bold; color:#ffffff;'>📅 {date_str} [{self._ticker_name}]</div>"
                f"<hr style='border:0; border-top:1px solid #334155; margin:4px 0;'>"
                f"<span style='color:#94a3b8;'>• 종가:</span> <span style='color:#38bdf8; font-weight:bold; font-size:13px;'>{close_p:,.0f}원</span>"
                f"</div>"
            )

        QToolTip.showText(QCursor.pos(), lines, self.canvas)

    def _on_figure_leave(self, event):
        self._hide_tooltip()

    def _hide_tooltip(self):
        needs_redraw = False
        if self._cursor_line and self._cursor_line.get_visible():
            self._cursor_line.set_visible(False)
            needs_redraw = True
        if self._highlight_dot and self._highlight_dot.get_visible():
            self._highlight_dot.set_visible(False)
            needs_redraw = True
        if needs_redraw:
            self.canvas.draw_idle()
        QToolTip.hideText()

