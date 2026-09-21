"""
ui/widgets/ticker_banner.py
상단 전광판 (Ticker Banner) 위젯.
- comment.txt 파일에서 코멘트 목록을 로드하여 3초 주기로 롤링 표시
- 부드러운 페이드(Fade In/Out) 애니메이션 전환 효과
- 이전/다음 수동 탐색 버튼, 일시정지/재생 및 마우스 오버 시 일시정지 지원
- 세련된 다크 테마 디자인
"""

from __future__ import annotations
import os
import logging
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QGraphicsOpacityEffect, QWidget, QSizePolicy
)
from PySide6.QtGui import QCursor

from core.paths import get_project_root

logger = logging.getLogger("RetirementPortfolio.TickerBanner")


class TickerBanner(QFrame):
    """
    UI 최상단 전광판 배너 위젯.
    """
    def __init__(self, comment_file: Optional[Path] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("TickerBanner")
        self.setFixedHeight(42)

        self.comment_file = comment_file or (get_project_root() / "comment.txt")
        self.comments: List[str] = self._load_comments()
        self.current_index = 0
        self.is_paused = False

        self._setup_ui()
        self._setup_animation()

        # 3초 유지 타이머 설정 (요구사항: 각 코멘트 마다 3초를 유지한다)
        self.timer = QTimer(self)
        self.timer.setInterval(3000)
        self.timer.timeout.connect(self.next_comment)

        if self.comments:
            self._display_comment(0, animate=False)
            self.timer.start()

    def _load_comments(self) -> List[str]:
        """comment.txt 파일에서 코멘트 목록을 읽어옵니다."""
        if not self.comment_file.exists():
            logger.warning("comment.txt 파일을 찾을 수 없습니다: %s", self.comment_file)
            return [
                "원칙 중심의 기계적 분할 매수로 시장의 노이즈를 이겨냅니다.",
                "네 손가락이 투자전략이면 벌써 워런 버핏이다.",
                "주가가 떨어진 게 아니다. 네 평정심이 떨어진 거다.",
            ]

        # 인코딩 순차 시도 (utf-8, cp949, euc-kr)
        for enc in ["utf-8", "cp949", "euc-kr"]:
            try:
                with open(self.comment_file, "r", encoding=enc) as f:
                    lines = [line.strip() for line in f if line.strip()]
                    if lines:
                        logger.info("comment.txt에서 %d개 코멘트 로드 완료 (인코딩: %s)", len(lines), enc)
                        return lines
            except UnicodeDecodeError:
                continue
            except Exception as e:
                logger.error("comment.txt 로드 중 오류: %s", e)
                break

        return ["계획대로 분할 매수하고, 감정을 배제한 투자를 실천하세요."]

    def _setup_ui(self):
        """위젯 UI 레이아웃 및 스타일을 구성합니다."""
        self.setStyleSheet("""
            #TickerBanner {
                background-color: #0b111e;
                border-bottom: 1px solid #1e293b;
            }
            #TickerBadge {
                background-color: #1e293b;
                color: #38bdf8;
                font-size: 11px;
                font-weight: bold;
                border-radius: 10px;
                padding: 3px 10px;
                border: 1px solid #334155;
            }
            #TickerText {
                color: #f1f5f9;
                font-size: 13px;
                font-weight: 500;
            }
            #TickerCount {
                color: #64748b;
                font-size: 11px;
                font-weight: 600;
                padding-right: 4px;
            }
            .ticker-btn {
                background-color: transparent;
                color: #94a3b8;
                border: none;
                border-radius: 4px;
                font-size: 11px;
                padding: 2px 6px;
                font-weight: bold;
            }
            .ticker-btn:hover {
                background-color: #1e293b;
                color: #f8fafc;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 2, 16, 2)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignVCenter)

        # 1. 좌측 뱃지 태그
        self.badge = QLabel("⚡ 멘탈 전광판")
        self.badge.setObjectName("TickerBadge")
        layout.addWidget(self.badge)

        # 2. 중앙 롤링 텍스트 라벨 (페이드 효과 적용)
        self.text_label = QLabel()
        self.text_label.setObjectName("TickerText")
        self.text_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.text_label.setTextInteractionFlags(Qt.NoTextInteraction)
        self.text_label.setCursor(QCursor(Qt.PointingHandCursor))
        self.text_label.setToolTip("클릭하면 다음 명언으로 즉시 이동합니다 (마우스 오버 시 일시정지)")
        self.text_label.mousePressEvent = lambda e: self.next_comment()
        layout.addWidget(self.text_label)

        # 3. 우측 페이지 카운터
        self.count_label = QLabel("1/1")
        self.count_label.setObjectName("TickerCount")
        layout.addWidget(self.count_label)

        # 4. 이전 / 다음 / 일시정지 컨트롤 버튼
        self.btn_prev = QPushButton("◀")
        self.btn_prev.setProperty("class", "ticker-btn")
        self.btn_prev.setToolTip("이전 코멘트")
        self.btn_prev.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_prev.clicked.connect(self.prev_comment)
        layout.addWidget(self.btn_prev)

        self.btn_pause = QPushButton("⏸")
        self.btn_pause.setProperty("class", "ticker-btn")
        self.btn_pause.setToolTip("일시 정지 / 재생")
        self.btn_pause.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_pause.clicked.connect(self.toggle_pause)
        layout.addWidget(self.btn_pause)

        self.btn_next = QPushButton("▶")
        self.btn_next.setProperty("class", "ticker-btn")
        self.btn_next.setToolTip("다음 코멘트")
        self.btn_next.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_next.clicked.connect(self.next_comment)
        layout.addWidget(self.btn_next)

    def _setup_animation(self):
        """텍스트 전환용 페이드 아웃/인 애니메이션 설정"""
        self.opacity_effect = QGraphicsOpacityEffect(self.text_label)
        self.text_label.setGraphicsEffect(self.opacity_effect)

        self.anim_fade_out = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim_fade_out.setDuration(220)
        self.anim_fade_out.setStartValue(1.0)
        self.anim_fade_out.setEndValue(0.0)
        self.anim_fade_out.setEasingCurve(QEasingCurve.InOutQuad)

        self.anim_fade_in = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim_fade_in.setDuration(220)
        self.anim_fade_in.setStartValue(0.0)
        self.anim_fade_in.setEndValue(1.0)
        self.anim_fade_in.setEasingCurve(QEasingCurve.InOutQuad)

        self.anim_fade_out.finished.connect(self._on_fade_out_finished)

    def _display_comment(self, index: int, animate: bool = True):
        """지정된 인덱스의 코멘트를 표시합니다."""
        if not self.comments:
            self.text_label.setText("표시할 코멘트가 없습니다.")
            self.count_label.setText("0/0")
            return

        self.current_index = index % len(self.comments)
        text = self.comments[self.current_index]
        count_text = f"{self.current_index + 1}/{len(self.comments)}"

        self.count_label.setText(count_text)
        if animate:
            self._target_text = f"“{text}”"
            self.anim_fade_out.start()
        else:
            self.text_label.setText(f"“{text}”")
            self.opacity_effect.setOpacity(1.0)

    def _on_fade_out_finished(self):
        """페이드 아웃 완료 후 텍스트를 교체하고 페이드 인을 시작합니다."""
        self.text_label.setText(getattr(self, "_target_text", ""))
        self.count_label.setText(getattr(self, "_target_count", ""))
        self.anim_fade_in.start()

    def next_comment(self):
        """다음 코멘트로 전환합니다."""
        if not self.comments:
            return
        next_idx = (self.current_index + 1) % len(self.comments)
        self._display_comment(next_idx, animate=True)
        if not self.is_paused:
            self.timer.start()  # 타이머 리셋하여 3초 보장

    def prev_comment(self):
        """이전 코멘트로 전환합니다."""
        if not self.comments:
            return
        prev_idx = (self.current_index - 1 + len(self.comments)) % len(self.comments)
        self._display_comment(prev_idx, animate=True)
        if not self.is_paused:
            self.timer.start()

    def toggle_pause(self):
        """자동 롤링 일시정지/재생을 토글합니다."""
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

    def enterEvent(self, event):
        """마우스가 배너 위에 올라오면 사용자가 편하게 읽도록 자동 롤링을 일시 중지합니다."""
        if not self.is_paused:
            self.timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """마우스가 배너를 벗어나면 자동 롤링을 재개합니다."""
        if not self.is_paused:
            self.timer.start()
        super().leaveEvent(event)
