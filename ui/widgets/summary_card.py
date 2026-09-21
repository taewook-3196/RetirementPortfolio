"""
ui/widgets/summary_card.py
상단 KPI 메트릭 및 요약 정보를 보여주는 프리미엄 카드 위젯.
"""

from __future__ import annotations
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt


class SummaryCard(QFrame):
    def __init__(
        self,
        title: str,
        value: str = "0원",
        badge: str = "",
        badge_type: str = "neutral",  # positive, negative, neutral, accent
        parent=None,
    ):
        super().__init__(parent)
        self.setProperty("class", "card")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)

        # 상단 타이틀 및 배지 행
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self.title_label = QLabel(title)
        self.title_label.setProperty("class", "card-title")
        top_row.addWidget(self.title_label)

        top_row.addStretch()

        self.badge_label = QLabel(badge)
        self.badge_label.setProperty("class", "card-badge")
        self.set_badge(badge, badge_type)
        top_row.addWidget(self.badge_label)

        layout.addLayout(top_row)

        # 메인 값 라벨
        self.value_label = QLabel(value)
        self.value_label.setProperty("class", "card-value")
        layout.addWidget(self.value_label)

    def set_value(self, value: str):
        self.value_label.setText(value)

    def set_badge(self, text: str, badge_type: str = "neutral"):
        if not text:
            self.badge_label.setVisible(False)
            return

        self.badge_label.setVisible(True)
        self.badge_label.setText(text)

        colors = {
            "positive": "background-color: #064e3b; color: #34d399;",
            "negative": "background-color: #7f1d1d; color: #f87171;",
            "accent": "background-color: #1e3a8a; color: #60a5fa;",
            "neutral": "background-color: #1e293b; color: #94a3b8;",
        }
        style = colors.get(badge_type, colors["neutral"])
        self.badge_label.setStyleSheet(style + " border-radius: 4px; padding: 2px 6px;")
