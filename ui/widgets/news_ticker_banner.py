"""
ui/widgets/news_ticker_banner.py
UI 최하단 실시간 뉴스 전광판 (News Ticker Banner) 위젯.
- 네이버 금융 및 구글 뉴스 RSS 피드를 받아 4초 주기로 부드럽게 롤링
- 기사 제목 클릭 시 기본 웹브라우저로 기사 원문 페이지 열기 (QDesktopServices)
- 뉴스 출처, 발행 시간, 카테고리/종목 뱃지 표시
- 마우스 오버 시 일시 정지, 이전/다음 수동 탐색 및 수동 새로고침 버튼 지원
"""

from __future__ import annotations
import logging
from typing import List, Dict, Any, Optional

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QUrl, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QGraphicsOpacityEffect, QWidget, QSizePolicy
)
from PySide6.QtGui import QCursor, QDesktopServices

logger = logging.getLogger("RetirementPortfolio.NewsTickerBanner")


class NewsTickerBanner(QFrame):
    """
    UI 최하단 뉴스 전광판 위젯
    """
    refresh_requested = Signal()  # 수동 새로고침 요청 시그널

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("NewsTickerBanner")
        self.setFixedHeight(42)

        self.news_feed: List[Dict[str, Any]] = []
        self.current_index = 0
        self.is_paused = False
        self.current_link = ""

        self._setup_ui()
        self._setup_animation()

        # 4초 유지 타이머
        self.timer = QTimer(self)
        self.timer.setInterval(4000)
        self.timer.timeout.connect(self.next_news)

    def _setup_ui(self):
        """다크 테마 스타일 및 레이아웃 구성"""
        self.setStyleSheet("""
            #NewsTickerBanner {
                background-color: #090d16;
                border-top: 1px solid #1e293b;
            }
            #NewsBadge {
                background-color: #1e3a8a;
                color: #60a5fa;
                font-size: 11px;
                font-weight: bold;
                border-radius: 9px;
                padding: 3px 10px;
                border: 1px solid #2563eb;
            }
            #NewsSource {
                color: #94a3b8;
                font-size: 12px;
                font-weight: 500;
            }
            #NewsTitle {
                color: #f8fafc;
                font-size: 13px;
                font-weight: 500;
            }
            #NewsTitle:hover {
                color: #38bdf8;
                text-decoration: underline;
            }
            #NewsCount {
                color: #64748b;
                font-size: 11px;
                font-weight: 600;
                padding-right: 4px;
            }
            .news-btn {
                background-color: transparent;
                color: #94a3b8;
                border: none;
                border-radius: 4px;
                font-size: 11px;
                padding: 2px 6px;
                font-weight: bold;
            }
            .news-btn:hover {
                background-color: #1e293b;
                color: #f8fafc;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 2, 16, 2)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignVCenter)

        # 1. 뉴스 카테고리 / 종목 뱃지
        self.badge = QLabel("📰 실시간 뉴스")
        self.badge.setObjectName("NewsBadge")
        layout.addWidget(self.badge)

        # 2. 언론사 표기
        self.source_label = QLabel("")
        self.source_label.setObjectName("NewsSource")
        layout.addWidget(self.source_label)

        # 3. 중앙 뉴스 제목 (클릭 시 웹브라우저 오픈)
        self.title_label = QLabel("최신 시장 및 종목 뉴스를 불러오는 중입니다...")
        self.title_label.setObjectName("NewsTitle")
        self.title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.title_label.setCursor(QCursor(Qt.PointingHandCursor))
        self.title_label.setToolTip("클릭하면 웹브라우저로 기사 원문을 엽니다 (마우스 오버 시 일시 정지)")
        self.title_label.mousePressEvent = self._on_title_clicked
        layout.addWidget(self.title_label)

        # 4. 카운터 (예: 1/20)
        self.count_label = QLabel("0/0")
        self.count_label.setObjectName("NewsCount")
        layout.addWidget(self.count_label)

        # 5. 이전 / 다음 / 일시정지 / 새로고침 컨트롤
        self.btn_prev = QPushButton("◀")
        self.btn_prev.setProperty("class", "news-btn")
        self.btn_prev.setToolTip("이전 뉴스")
        self.btn_prev.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_prev.clicked.connect(self.prev_news)
        layout.addWidget(self.btn_prev)

        self.btn_pause = QPushButton("⏸")
        self.btn_pause.setProperty("class", "news-btn")
        self.btn_pause.setToolTip("일시 정지 / 재생")
        self.btn_pause.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_pause.clicked.connect(self.toggle_pause)
        layout.addWidget(self.btn_pause)

        self.btn_next = QPushButton("▶")
        self.btn_next.setProperty("class", "news-btn")
        self.btn_next.setToolTip("다음 뉴스")
        self.btn_next.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_next.clicked.connect(self.next_news)
        layout.addWidget(self.btn_next)

        self.btn_refresh = QPushButton("🔄")
        self.btn_refresh.setProperty("class", "news-btn")
        self.btn_refresh.setToolTip("뉴스 지금 새로고침")
        self.btn_refresh.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_refresh.clicked.connect(self._on_refresh_clicked)
        layout.addWidget(self.btn_refresh)

    def _setup_animation(self):
        """부드러운 페이드 전환 효과"""
        self.opacity_effect = QGraphicsOpacityEffect(self.title_label)
        self.title_label.setGraphicsEffect(self.opacity_effect)

        self.anim_fade_out = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim_fade_out.setDuration(200)
        self.anim_fade_out.setStartValue(1.0)
        self.anim_fade_out.setEndValue(0.0)
        self.anim_fade_out.setEasingCurve(QEasingCurve.InOutQuad)

        self.anim_fade_in = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim_fade_in.setDuration(200)
        self.anim_fade_in.setStartValue(0.0)
        self.anim_fade_in.setEndValue(1.0)
        self.anim_fade_in.setEasingCurve(QEasingCurve.InOutQuad)

        self.anim_fade_out.finished.connect(self._on_fade_out_finished)

    def set_news_feed(self, feed: List[Dict[str, Any]]):
        """수집된 뉴스 피드를 주입하고 전광판 롤링을 시작합니다."""
        self.news_feed = feed or []
        self.current_index = 0

        if not self.news_feed:
            self.title_label.setText("최신 뉴스 데이터가 없습니다.")
            self.count_label.setText("0/0")
            self.source_label.setText("")
            self.current_link = ""
            self.timer.stop()
            return

        self._display_news(0, animate=False)
        if not self.is_paused:
            self.timer.start()

    def _display_news(self, index: int, animate: bool = True):
        """특정 인덱스의 뉴스를 화면에 표시합니다."""
        if not self.news_feed:
            return

        self.current_index = index % len(self.news_feed)
        item = self.news_feed[self.current_index]

        tag = item.get("tag", "뉴스")
        title = item.get("title", "")
        press = item.get("press", "")
        link = item.get("link", "")
        self.current_link = link

        # 뱃지 및 출처 업데이트
        self.badge.setText(f"📰 {tag}")
        self.source_label.setText(f"[{press}]" if press else "")
        self.count_label.setText(f"{self.current_index + 1}/{len(self.news_feed)}")

        if animate:
            self._target_title = title
            self.anim_fade_out.start()
        else:
            self.title_label.setText(title)
            self.opacity_effect.setOpacity(1.0)

    def _on_fade_out_finished(self):
        """페이드 아웃 완료 후 제목 교체 및 페이드 인"""
        self.title_label.setText(getattr(self, "_target_title", ""))
        self.anim_fade_in.start()

    def next_news(self):
        """다음 뉴스로 전환"""
        if not self.news_feed:
            return
        next_idx = (self.current_index + 1) % len(self.news_feed)
        self._display_news(next_idx, animate=True)
        if not self.is_paused:
            self.timer.start()

    def prev_news(self):
        """이전 뉴스로 전환"""
        if not self.news_feed:
            return
        prev_idx = (self.current_index - 1 + len(self.news_feed)) % len(self.news_feed)
        self._display_news(prev_idx, animate=True)
        if not self.is_paused:
            self.timer.start()

    def toggle_pause(self):
        """자동 롤링 일시정지/재생 토글"""
        if self.is_paused:
            self.is_paused = False
            self.timer.start()
            self.btn_pause.setText("⏸")
            self.btn_pause.setToolTip("일시 정지")
        else:
            self.is_paused = True
            self.timer.stop()
            self.btn_pause.setText("▶")
            self.btn_pause.setToolTip("재생")

    def _on_title_clicked(self, event):
        """기사 제목 클릭 시 기본 웹브라우저로 원문 기사 오픈"""
        if self.current_link:
            QDesktopServices.openUrl(QUrl(self.current_link))

    def _on_refresh_clicked(self):
        """새로고침 버튼 클릭 시 시그널 발송"""
        self.badge.setText("🔄 수집 중...")
        self.refresh_requested.emit()

    def enterEvent(self, event):
        """마우스가 배너 위에 머물면 읽기 편하도록 타이머 일시 정지"""
        if not self.is_paused:
            self.timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """마우스가 벗어나면 롤링 재개"""
        if not self.is_paused:
            self.timer.start()
        super().leaveEvent(event)
