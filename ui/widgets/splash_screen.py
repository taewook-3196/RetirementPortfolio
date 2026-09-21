"""
ui/widgets/splash_screen.py
프로그램 시작 시 표출되는 3D 황금복돼지 인트로 스플래시 애니메이션 위젯.
- 프레임리스 반투명 윈도우 및 골드 앰비언트 글로우 디자인
- QGraphicsOpacityEffect 버그(블랙 박스 현상)를 완벽히 제거하고 DWM 네이티브 윈도우 투명도 사용
- 황금복돼지 탄성 바운스(Bounce) 및 플로팅(Floating) 애니메이션
- "복(福)을 부르는 퇴직연금" 축복 메시지 및 실시간 로딩 상태 연출
- 마우스 클릭/키 입력 시 즉시 스킵(Instant Skip) 지원
"""

from __future__ import annotations
import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint, Signal, QSize
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QProgressBar,
    QApplication,
)
from PySide6.QtGui import QPixmap, QCursor, QGuiApplication, QPainter, QPainterPath, QMovie
from core.paths import get_golden_pig_path, get_golden_pig_gif_path

logger = logging.getLogger("RetirementPortfolio.SplashScreen")


class GoldenPigSplashScreen(QWidget):
    """3D 황금복돼지 인트로 스플래시 애니메이션 창"""

    finished = Signal()

    def __init__(
        self,
        image_path: Optional[Path] = None,
        min_display_ms: int = 2000,
        duration_ms: Optional[int] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.image_path = image_path or get_golden_pig_path()
        self.min_display_ms = duration_ms if duration_ms is not None else min_display_ms
        self._auto_close = duration_ms is not None
        self._is_closing = False
        self._ready_to_close = False
        self._min_timer_expired = False

        self._init_window()
        self._setup_ui()
        self._setup_animations()

    def paintEvent(self, event):
        # DWM 컴포지터에서 검은색 잔상이 생기지 않도록 배경을 완전 투명으로 클리어
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)

    def _init_window(self):
        # 블랙 박스 현상을 유발하는 Qt.SplashScreen 플래그 대신 깔끔한 FramelessWindow 사용
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(480, 560)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setWindowOpacity(1.0)

        # 화면 정중앙 배치
        screen = QGuiApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(
                geo.x() + (geo.width() - self.width()) // 2,
                geo.y() + (geo.height() - self.height()) // 2,
            )

    def _setup_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 12, 12, 12)

        # 1. 골드 앰비언트 글로우 카드 프레임 (모서리 24px 라운드)
        self.card = QFrame(self)
        self.card.setObjectName("SplashCard")
        self.card.setStyleSheet("""
            #SplashCard {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #141c2c, stop:0.5 #0c121e, stop:1 #060911);
                border: 2px solid #f59e0b;
                border-radius: 24px;
            }
            #SplashCard QLabel {
                background: transparent;
            }
            #SplashCard QWidget {
                background: transparent;
            }
            #SplashBadge {
                background-color: #3b2204;
                color: #fbbf24;
                font-size: 12px;
                font-weight: bold;
                border: 1px solid #d97706;
                border-radius: 12px;
                padding: 4px 14px;
            }
            #PigTitle {
                color: #fef08a;
                font-size: 20px;
                font-weight: 800;
            }
            #PigSubtitle {
                color: #e2e8f0;
                font-size: 13px;
                font-weight: 500;
            }
            #StatusText {
                color: #94a3b8;
                font-size: 11px;
                font-weight: 500;
            }
            QProgressBar {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 4px;
                height: 6px;
                text-align: center;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #f59e0b, stop:1 #fbbf24);
                border-radius: 4px;
            }
        """)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(24, 24, 24, 20)
        card_layout.setSpacing(12)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 상단 복(福) 뱃지
        badge_box = QHBoxLayout()
        badge_box.addStretch()
        self.badge = QLabel("✨ 복(福)이 굴러들어오는 퇴직연금 ETF")
        self.badge.setObjectName("SplashBadge")
        badge_box.addWidget(self.badge)
        badge_box.addStretch()
        card_layout.addLayout(badge_box)

        # 중앙 황금복돼지 이미지 컨테이너
        self.pig_container = QWidget(self.card)
        self.pig_container.setFixedHeight(270)
        pig_layout = QVBoxLayout(self.pig_container)
        pig_layout.setContentsMargins(0, 0, 0, 0)
        pig_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.pig_label = QLabel(self.pig_container)
        self.pig_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        gif_path = get_golden_pig_gif_path()
        if gif_path.exists():
            self.movie = QMovie(str(gif_path))
            self.movie.setScaledSize(QSize(260, 260))
            self.pig_label.setMovie(self.movie)
            self.pig_label.setStyleSheet("background: transparent;")
            self.movie.start()
        elif self.image_path.exists():
            orig_pix = QPixmap(str(self.image_path)).scaled(
                260, 260,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            # 둥근 모서리 및 부드러운 안티앨리어싱 마스크 적용
            rounded_pix = QPixmap(orig_pix.size())
            rounded_pix.fill(Qt.GlobalColor.transparent)
            painter = QPainter(rounded_pix)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            path = QPainterPath()
            path.addRoundedRect(0, 0, orig_pix.width(), orig_pix.height(), 20, 20)
            painter.setClipPath(path)
            painter.drawPixmap(0, 0, orig_pix)
            painter.end()
            self.pig_label.setPixmap(rounded_pix)
            self.pig_label.setStyleSheet("border: 1px solid #d97706; border-radius: 20px; background: transparent;")
        else:
            self.pig_label.setText("🐷")
            self.pig_label.setStyleSheet("font-size: 120px; background: transparent;")

        pig_layout.addWidget(self.pig_label)
        card_layout.addWidget(self.pig_container)

        # 축복 문구 타이틀
        self.title_label = QLabel("🐷 꿀꿀! 부자 되세요~")
        self.title_label.setObjectName("PigTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.title_label)

        # 서브 축복 문구
        self.sub_label = QLabel("오늘도 원칙 있는 분할 매수로 복리 대박을 기원합니다!")
        self.sub_label.setObjectName("PigSubtitle")
        self.sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.sub_label)

        card_layout.addSpacing(6)

        # 하단 상태 라벨 및 프로그레스 바
        self.status_label = QLabel("황금복돼지의 기운을 담아 시스템 로딩 중... (클릭 시 건너뛰기)")
        self.status_label.setObjectName("StatusText")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(15)
        self.progress_bar.setTextVisible(False)
        card_layout.addWidget(self.progress_bar)

        root_layout.addWidget(self.card)

    def _setup_animations(self):
        """황금복돼지 통통 튀는 바운스 효과 설정"""
        self._pig_target_pos = QPoint(0, 0)

        # 1. 황금복돼지 통통 튀는 바운스 효과 (위아래 탄성 튕기기)
        self.bounce_anim = QPropertyAnimation(self.pig_label, b"pos")
        self.bounce_anim.setDuration(800)
        self.bounce_anim.setEasingCurve(QEasingCurve.Type.OutBack)

        # 2. 최소 노출 시간 보장 타이머
        self.min_timer = QTimer(self)
        self.min_timer.setSingleShot(True)
        self.min_timer.setInterval(self.min_display_ms)
        self.min_timer.timeout.connect(self._on_min_timer_expired)

        # 3. 비상 탈출용 최대 타이머 (최대 대기 시간 후 자동 닫힘 보장)
        self.max_timer = QTimer(self)
        self.max_timer.setSingleShot(True)
        self.max_timer.setInterval(max(self.min_display_ms * 2, 5000))
        self.max_timer.timeout.connect(self.start_fade_out)

    def start_animation(self):
        """스플래시 창 표출 및 바운스 모션 시작"""
        self.show()
        QApplication.processEvents()

        # 라벨의 현재 좌표 기준으로 아래에서 통통 튕겨 올라오기
        p = self.pig_label.pos()
        self._pig_target_pos = p
        self.bounce_anim.setStartValue(QPoint(p.x(), p.y() + 32))
        self.bounce_anim.setEndValue(p)
        self.bounce_anim.start()

        self.min_timer.start()
        self.max_timer.start()

    def set_progress(self, percent: int, text: str = ""):
        """진행률 및 상태 텍스트 갱신 (화면 즉시 다시 그리기 보장)"""
        self.progress_bar.setValue(min(max(percent, 0), 100))
        if text:
            self.status_label.setText(text)
        QApplication.processEvents()

    def mark_ready(self):
        """백그라운드 로딩 완료 알림 (최소 표시 시간이 지났으면 즉시 페이드아웃, 아니면 대기)"""
        self._ready_to_close = True
        self.set_progress(100, "시스템 준비 완료! 🐷 부자 되세요~")
        if self._min_timer_expired:
            self.start_fade_out()

    def _on_min_timer_expired(self):
        """최소 표시 시간 도달 시 (로딩이 이미 끝났거나 단위테스트/자동모드면 페이드아웃)"""
        self._min_timer_expired = True
        if self._ready_to_close or self._auto_close:
            self.start_fade_out()

    def start_fade_out(self):
        """네이티브 윈도우 투명도를 이용한 부드러운 페이드아웃 (블랙 박스 없음)"""
        if self._is_closing:
            return
        self._is_closing = True

        self.fade_out = QPropertyAnimation(self, b"windowOpacity")
        self.fade_out.setDuration(250)
        self.fade_out.setStartValue(self.windowOpacity())
        self.fade_out.setEndValue(0.0)
        self.fade_out.setEasingCurve(QEasingCurve.Type.InCubic)
        self.fade_out.finished.connect(self._on_finished)
        self.fade_out.start()

    def _on_finished(self):
        """스플래시 종료 처리 및 finished 시그널 방출"""
        if hasattr(self, "min_timer") and self.min_timer.isActive():
            self.min_timer.stop()
        if hasattr(self, "max_timer") and self.max_timer.isActive():
            self.max_timer.stop()
        if hasattr(self, "movie") and self.movie.state() == QMovie.MovieState.Running:
            self.movie.stop()
        self.finished.emit()
        self.close()

    def mousePressEvent(self, event):
        """마우스 클릭 시 즉시 스킵"""
        self.start_fade_out()

    def keyPressEvent(self, event):
        """키 입력 시 즉시 스킵"""
        self.start_fade_out()
