"""
ui/main_window.py
메인 윈도우 및 좌측 사이드바 네비게이션 (프롬프트 43번 항목).
- 좌측: 6대 핵심 메뉴 (대시보드, 포트폴리오, 매수추천, 거래내역, 시장데이터, 설정)
- 상단: 페이지 타이틀, 시스템 상태 진단(62번 항목), 비동기 [시장 데이터 업데이트] 버튼
- 우측: QStackedWidget 기반 고성능 페이지 전환
"""

from __future__ import annotations
import logging
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QStackedWidget,
    QPushButton,
    QLabel,
    QButtonGroup,
    QFrame,
    QMessageBox,
    QApplication,
    QComboBox,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from core.config import AppConfig, load_config
from core.paths import get_icon_path
from database.repository import Repository
from services.market_data_service import MarketDataService
from services.portfolio_service import PortfolioService
from services.recommendation_service import RecommendationService
from ui.dashboard_page import DashboardPage
from ui.portfolio_page import PortfolioPage
from ui.recommendation_page import RecommendationPage
from ui.transactions_page import TransactionsPage
from ui.market_data_page import MarketDataPage
from ui.settings_page import SettingsPage
from ui.workers import PriceUpdateWorker, NewsUpdateWorker
from ui.widgets.ticker_banner import TickerBanner
from ui.widgets.news_ticker_banner import NewsTickerBanner
from services.news_service import NewsService

logger = logging.getLogger("RetirementPortfolio.MainWindow")


class MainWindow(QMainWindow):
    def __init__(self, repo: Repository, config: AppConfig | None = None):
        super().__init__()
        self.repo = repo
        self.config = config or load_config()

        # 서비스 레이어 초기화
        self.market_service = MarketDataService(self.repo, self.config)
        self.portfolio_service = PortfolioService(self.repo, self.config)
        self.rec_service = RecommendationService(
            self.repo, self.config, self.market_service, self.portfolio_service
        )
        self.news_service = NewsService()

        self._worker: PriceUpdateWorker | None = None
        self._news_worker: NewsUpdateWorker | None = None

        self._init_window()
        QApplication.processEvents()
        self._setup_ui()
        QApplication.processEvents()
        self._refresh_current_page()
        QApplication.processEvents()

    def _init_window(self):
        self.setWindowTitle("개인 퇴직연금 ETF 포트폴리오 관리 시스템")
        self.resize(1280, 850)
        self.setMinimumSize(1024, 700)
        icon_path = get_icon_path()
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 전체 수직 레이아웃 (최상단 전광판 + 하단 네비게이션/본문 + 최하단 뉴스 전광판)
        window_layout = QVBoxLayout(central_widget)
        window_layout.setContentsMargins(0, 0, 0, 0)
        window_layout.setSpacing(0)

        # 1. UI 제일 상단 전광판 (comment.txt 기반 3초 롤링)
        self.ticker_banner = TickerBanner(parent=self)
        window_layout.addWidget(self.ticker_banner)

        # 2. 중앙 메인 콘텐츠 컨테이너
        content_container = QWidget()
        window_layout.addWidget(content_container, 1)

        root_layout = QHBoxLayout(content_container)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. 좌측 사이드바 (Navigation)
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(210)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 16)
        sidebar_layout.setSpacing(4)

        title_lbl = QLabel("퇴직연금 ETF 포트폴리오")
        title_lbl.setObjectName("AppTitle")
        sub_lbl = QLabel("월간 매수 의사결정 지원")
        sub_lbl.setObjectName("AppSubtitle")
        sidebar_layout.addWidget(title_lbl)
        sidebar_layout.addWidget(sub_lbl)

        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)

        nav_items = [
            ("📊 대시보드", 0),
            ("💼 포트폴리오", 1),
            ("🎯 매수 추천", 2),
            ("📝 거래내역", 3),
            ("📈 시장 데이터", 4),
            ("⚙️ 환경 설정", 5),
        ]

        self.nav_buttons = []
        for text, idx in nav_items:
            btn = QPushButton(text)
            btn.setProperty("class", "nav-btn")
            btn.setCheckable(True)
            self.btn_group.addButton(btn, idx)
            sidebar_layout.addWidget(btn)
            self.nav_buttons.append(btn)

        sidebar_layout.addStretch()

        # 하단 시스템 진단 상태 (프롬프트 62번 항목)
        status_box = QFrame()
        status_box.setStyleSheet("background-color: #0f141c; margin: 8px; padding: 10px; border-radius: 6px;")
        status_layout = QVBoxLayout(status_box)
        status_layout.setSpacing(4)
        status_layout.addWidget(QLabel("<span style='color:#10b981;'>●</span> DB: SQLite 연결됨"))
        self.lbl_src_status = QLabel(f"<span style='color:#38bdf8;'>●</span> 소스: {self.config.data_source.upper()}")
        status_layout.addWidget(self.lbl_src_status)
        sidebar_layout.addWidget(status_box)

        root_layout.addWidget(sidebar)

        # 2. 우측 메인 영역 (헤더 + QStackedWidget)
        main_area = QWidget()
        main_layout = QVBoxLayout(main_area)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 상단 헤더
        header = QFrame()
        header.setObjectName("HeaderPanel")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(24, 12, 24, 12)
        header_layout.setSpacing(14)

        self.page_title = QLabel("대시보드")
        self.page_title.setObjectName("PageTitle")
        header_layout.addWidget(self.page_title)

        # 대시보드 텍스트 옆 계좌 선택 드롭다운 (프리미엄 멀티 계좌 연동)
        self.combo_account = QComboBox()
        self.combo_account.setObjectName("AccountSelectorComboBox")
        header_layout.addWidget(self.combo_account)

        header_layout.addStretch()

        # 비동기 시장 데이터 업데이트 버튼 (프롬프트 50, 51번 항목)
        self.btn_update = QPushButton("🔄 시장 데이터 업데이트")
        self.btn_update.setProperty("class", "primary-btn")
        self.btn_update.clicked.connect(self._start_price_update)
        header_layout.addWidget(self.btn_update)

        main_layout.addWidget(header)

        # 중앙 페이지 스택
        self.stack = QStackedWidget()

        available_tickers = [(e.ticker, e.name) for e in self.config.etfs] + [
            (w.ticker, w.name) for w in getattr(self.config, "watchlist", []) if w.ticker not in [e.ticker for e in self.config.etfs]
        ]

        self.page_dashboard = DashboardPage(self.portfolio_service, self.rec_service)
        self.page_portfolio = PortfolioPage(self.portfolio_service)
        self.page_rec = RecommendationPage(self.rec_service)
        self.page_tx = TransactionsPage(self.repo, available_tickers)
        self.page_tx.data_changed.connect(self._on_data_changed)
        self.page_market = MarketDataPage(self.market_service, self.config)
        self.page_market.watchlist_updated.connect(self._on_settings_saved)
        self.page_settings = SettingsPage(self.config, self.repo)
        self.page_settings.settings_saved.connect(self._on_settings_saved)

        self.stack.addWidget(self.page_dashboard)
        self.stack.addWidget(self.page_portfolio)
        self.stack.addWidget(self.page_rec)
        self.stack.addWidget(self.page_tx)
        self.stack.addWidget(self.page_market)
        self.stack.addWidget(self.page_settings)

        main_layout.addWidget(self.stack)
        root_layout.addWidget(main_area)

        # 계좌 드롭다운 데이터 채우기 및 이벤트 연결
        self._populate_account_selector(keep_selection=False)
        self.combo_account.currentIndexChanged.connect(self._on_account_changed)

        # 네비게이션 시그널 연결
        self.btn_group.idClicked.connect(self._switch_page)
        self.nav_buttons[0].setChecked(True)

        # 3. UI 제일 하단 뉴스 전광판 (하이브리드 뉴스 4초 롤링)
        self.news_ticker = NewsTickerBanner(parent=self)
        self.news_ticker.refresh_requested.connect(self._start_news_update)
        window_layout.addWidget(self.news_ticker)

        # 뉴스 자동 수집 시작 및 15분 주기 자동 갱신
        self._start_news_update()
        self.news_timer = QTimer(self)
        self.news_timer.setInterval(900000)  # 15분
        self.news_timer.timeout.connect(self._start_news_update)
        self.news_timer.start()

    def _populate_account_selector(self, keep_selection: bool = True):
        current_data = (
            self.combo_account.currentData()
            if keep_selection and self.combo_account.count() > 0
            else None
        )
        self.combo_account.blockSignals(True)
        self.combo_account.clear()

        # 1. 전체 계좌 (통합)
        self.combo_account.addItem("🌐 전체 계좌 (통합)", None)

        # 2. 등록된 개별 계좌들
        accs = self.repo.get_accounts()
        default_idx = 0
        for idx, a in enumerate(accs, start=1):
            label = f"🏦 {a.account_name}"
            if a.broker:
                label += f" ({a.broker})"
            if a.is_default:
                label += " [기본]"
            self.combo_account.addItem(label, a.id)
            if a.is_default and current_data is None:
                default_idx = idx

        # 선택 복원 또는 기본 계좌 선택
        if current_data is not None:
            found = False
            for i in range(self.combo_account.count()):
                if self.combo_account.itemData(i) == current_data:
                    self.combo_account.setCurrentIndex(i)
                    found = True
                    break
            if not found:
                self.combo_account.setCurrentIndex(default_idx)
        else:
            self.combo_account.setCurrentIndex(default_idx)

        self.combo_account.blockSignals(False)

    def _get_current_account_id(self) -> int | None:
        if hasattr(self, "combo_account") and self.combo_account.count() > 0:
            return self.combo_account.currentData()
        return None

    def _on_account_changed(self):
        self._refresh_current_page()

    def _switch_page(self, index: int):
        self.stack.setCurrentIndex(index)
        titles = ["대시보드", "포트폴리오 상세", "월간 매수 추천", "거래내역 관리", "시장 데이터 분석", "환경 설정"]
        if 0 <= index < len(titles):
            self.page_title.setText(titles[index])

        # 계좌 선택 드롭다운 노출 여부 (대시보드, 포트폴리오, 매수추천, 거래내역)
        self.combo_account.setVisible(index in (0, 1, 2, 3))
        self._refresh_current_page()

    def _refresh_current_page(self):
        idx = self.stack.currentIndex()
        acc_id = self._get_current_account_id()
        if idx == 0:
            self.page_dashboard.refresh(account_id=acc_id)
        elif idx == 1:
            self.page_portfolio.refresh(account_id=acc_id)
        elif idx == 2:
            self.page_rec.refresh(account_id=acc_id)
        elif idx == 3:
            self.page_tx.refresh(account_id=acc_id)
        elif idx == 4:
            self.page_market.refresh()
        elif idx == 5:
            self.page_settings.refresh()

    def _on_data_changed(self):
        """거래 등이 변경되었을 때 모든 페이지를 최신화"""
        self._refresh_current_page()

    def _on_settings_saved(self):
        """설정 변경 시 인스턴스 갱신 및 UI 업데이트"""
        self.config = load_config()
        self.lbl_src_status.setText(f"<span style='color:#38bdf8;'>●</span> 소스: {self.config.data_source.upper()}")
        self.portfolio_service.config = self.config
        self.market_service.config = self.config
        self.rec_service.config = self.config
        self.page_settings.config = self.config
        all_tickers = [(e.ticker, e.name) for e in self.config.etfs] + [
            (w.ticker, w.name) for w in getattr(self.config, "watchlist", []) if w.ticker not in [e.ticker for e in self.config.etfs]
        ]
        self.page_tx.tickers = all_tickers
        self.page_market.update_etf_list(self.config)
        self._populate_account_selector(keep_selection=True)
        self._refresh_current_page()
        self._start_news_update()

    def _start_news_update(self):
        """비동기 QThread 작업자로 최신 뉴스 수집 시작"""
        if self._news_worker and self._news_worker.isRunning():
            return
        mode = getattr(self.config, "news_filter_mode", "all")
        self._news_worker = NewsUpdateWorker(
            self.news_service,
            mode=mode,
            etfs=self.config.etfs,
            watchlist=getattr(self.config, "watchlist", [])
        )
        self._news_worker.finished_signal.connect(self._on_news_updated)
        self._news_worker.error_signal.connect(self._on_news_error)
        self._news_worker.start()

    def _on_news_updated(self, feed: list):
        self.news_ticker.set_news_feed(feed)

    def _on_news_error(self, err: str):
        logger.warning("뉴스 수집 비동기 오류: %s", err)

    def _start_price_update(self):
        """비동기 QThread 작업자로 시장 데이터 수집 시작 (UI 멈춤 방지)"""
        if self._worker and self._worker.isRunning():
            return

        self.btn_update.setEnabled(False)
        self.btn_update.setText("데이터 수집 중...")

        self._worker = PriceUpdateWorker(self.market_service)
        self._worker.finished_signal.connect(self._on_update_finished)
        self._worker.error_signal.connect(self._on_update_error)
        self._worker.start()

    def _on_update_finished(self, result: dict):
        self.btn_update.setEnabled(True)
        self.btn_update.setText("🔄 시장 데이터 업데이트")
        saved = result.get("saved_count", 0)
        source = result.get("data_source", "")
        QMessageBox.information(
            self,
            "업데이트 완료",
            f"시장 데이터 업데이트가 완료되었습니다.\n- 출처: {source}\n- 저장된 데이터: {saved}건",
        )
        self._refresh_current_page()

    def _on_update_error(self, err_msg: str):
        self.btn_update.setEnabled(True)
        self.btn_update.setText("🔄 시장 데이터 업데이트")
        QMessageBox.critical(self, "업데이트 오류", f"시장 데이터 갱신 중 오류가 발생했습니다:\n{err_msg}")

    def closeEvent(self, event):
        """윈도우 종료 시 백그라운드 워커 및 타이머 안전 종료"""
        if hasattr(self, "news_timer") and self.news_timer.isActive():
            self.news_timer.stop()
        if self._news_worker and self._news_worker.isRunning():
            self._news_worker.terminate()
            self._news_worker.wait(1000)
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait(1000)
        super().closeEvent(event)
