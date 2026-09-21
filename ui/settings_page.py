"""
ui/settings_page.py
설정 및 데이터베이스 백업/복원 화면 (프롬프트 13번, 14번, 53번, 54번 항목).
- 초기 투자금, 월 기본매수, 최대 추가매수 한도 설정
- ETF 목표비중 및 종목코드 편집 및 합계 100% 검증
- SQLite Native Backup API 기반 백업 및 복원
"""

from __future__ import annotations
import os
import webbrowser
import logging
from typing import Optional
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPushButton,
    QSpinBox,
    QDoubleSpinBox,
    QLineEdit,
    QMessageBox,
    QFileDialog,
    QLabel,
    QFrame,
    QComboBox,
    QDialog,
    QCheckBox,
    QScrollArea,
    QTimeEdit,
    QTextEdit,
    QSlider,
)
from PySide6.QtCore import Qt, Signal, QTime
from core.config import AppConfig, ETFConfig, MorningReportConfig, save_config
from database.repository import Repository
from strategy.cycle_helper import format_cycle_description
from services.daily_report_service import DailyReportService
from services.kakao_service import KakaoService
from services.github_service import GitHubService
from services.gemini_service import GeminiService, INVESTMENT_STANCE_PROFILES, STANCE_KEYS

logger = logging.getLogger("RetirementPortfolio.SettingsPage")


class GitHubGuideDialog(QDialog):
    """GitHub Personal Access Token (PAT) 발급 가이드 다이얼로그"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GitHub 클라우드 연동 토큰 발급 안내")
        self.setFixedSize(540, 500)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title = QLabel("☁️ GitHub Personal Access Token 발급 가이드 (1분 소요)")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #f8fafc;")
        layout.addWidget(title)

        guide_text = QTextEdit()
        guide_text.setReadOnly(True)
        guide_text.setStyleSheet(
            "background-color: #1e293b; color: #e2e8f0; font-size: 13px; line-height: 1.6; "
            "border: 1px solid #334155; border-radius: 8px; padding: 10px;"
        )
        guide_text.setHtml("""
        <ol style="margin-left: -15px;">
            <li><b>GitHub 토큰 설정 페이지 접속:</b><br>
                <a href="https://github.com/settings/tokens" style="color: #60a5fa;">https://github.com/settings/tokens</a> 에 접속하여 로그인합니다.
            </li><br>
            <li><b>토큰 생성 시작:</b><br>
                우측 상단 <b>[Generate new token] &gt; [Generate new token (classic)]</b>을 클릭합니다.
            </li><br>
            <li><b>토큰 이름 및 만료일 설정:</b><br>
                Note에 'Portfolio-Manager' 입력, Expiration을 'No expiration'으로 설정합니다.
            </li><br>
            <li><b>필수 권한(Scopes) 체크:</b><br>
                ☑️ <b>repo</b> (저장소 코드 및 커밋 접근 권한)<br>
                ☑️ <b>workflow</b> (GitHub Actions 워크플로우 On/Off 제어 권한)
            </li><br>
            <li><b>토큰 생성 및 복사:</b><br>
                페이지 맨 아래 [Generate token] 클릭 후 생성된 토큰(<code>ghp_...</code>)을 복사하여 앱에 붙여넣으세요!
            </li>
        </ol>
        <p style="color: #94a3b8; font-size: 12px; margin-top: 5px;">
            💡 <b>팁</b>: 저장소 입력란에는 <code>내아이디/저장소이름</code> 형태로 입력하세요. (상세 매뉴얼: <b>auto_kakaotalk_service.txt</b>)
        </p>
        """)
        layout.addWidget(guide_text)

        btn_box = QHBoxLayout()
        btn_open_gh = QPushButton("🌐 GitHub 토큰 발급 페이지 열기")
        btn_open_gh.setProperty("class", "secondary-btn")
        btn_open_gh.clicked.connect(lambda: webbrowser.open("https://github.com/settings/tokens"))
        btn_box.addWidget(btn_open_gh)

        btn_box.addStretch()

        btn_close = QPushButton("확인")
        btn_close.setProperty("class", "primary-btn")
        btn_close.setFixedWidth(80)
        btn_close.clicked.connect(self.accept)
        btn_box.addWidget(btn_close)

        layout.addLayout(btn_box)


class KakaoGuideDialog(QDialog):
    """카카오톡 REST API 키 및 메시지 발송 토큰 발급 가이드 다이얼로그"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("카카오톡 연동 가이드 및 토큰 발급 안내")
        self.setFixedSize(620, 620)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title = QLabel("📱 카카오톡 '나에게 보내기' 토큰 발급 (무료, 2분 완성)")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #f8fafc;")
        layout.addWidget(title)

        guide_text = QTextEdit()
        guide_text.setReadOnly(True)
        guide_text.setStyleSheet(
            "background-color: #1e293b; color: #e2e8f0; font-size: 13px; line-height: 1.6; "
            "border: 1px solid #334155; border-radius: 8px; padding: 12px;"
        )
        guide_text.setHtml("""
        <ol style="margin-left: -15px;">
            <li><b>카카오 개발자 사이트 접속:</b><br>
                <a href="https://developers.kakao.com" style="color: #60a5fa;">https://developers.kakao.com</a> 로그인 &gt; 애플리케이션 추가 (이름: 포트폴리오 매니저)
            </li><br>
            <li><b>REST API 키 확인 (최신 UI 위치):</b><br>
                좌측 사이드바 <b>[앱 설정] &gt; [앱] &gt; [플랫폼 키]</b> 클릭 &gt; 
                <b>[[대표] Default Rest API Key]</b> 카드의 32자리 키를 복사합니다.
            </li><br>
            <li><b>Redirect URI 등록 및 클라이언트 시크릿 확인 (필수):</b><br>
                • <b>[[대표] Default Rest API Key]</b> 카드를 클릭하여 수정 화면 진입<br>
                • '카카오 로그인 리다이렉트 URI'에 <code>https://localhost</code> 입력 후 <b>[+]</b> 클릭 &gt; 하단 <b>[저장]</b><br>
                • ⚠️ <b>클라이언트 시크릿</b>: 반드시 <b>[비활성화]</b> 상태여야 합니다. (KOE010 방지)
            </li><br>
            <li><b>카카오 로그인 & 메시지 전송 활성화:</b><br>
                • 좌측 <b>[제품 설정] &gt; [카카오 로그인] &gt; [일반]</b> &gt; 상태를 <b>'ON'</b>으로 변경<br>
                • 좌측 <b>[동의항목]</b> &gt; <b>'카카오톡 메시지 전송'</b>의 [설정] &gt; <b>[이용 중 동의]</b> 후 저장
            </li><br>
            <li><b>도메인 등록 (스마트폰 리포트 버튼 연결 필수):</b><br>
                • 좌측 <b>[앱 설정] &gt; [플랫폼] &gt; [Web] &gt; [사이트 도메인]</b><br>
                • <b>사이트 도메인</b>에 아래 주소를 입력 후 [저장]합니다:<br>
                &nbsp;&nbsp;<code>https://taewook-3196.github.io</code><br>
                <span style="color: #f87171; font-size: 11px; font-weight: bold;">⚠️ 주의: 사이트 도메인에 <code>https://localhost</code>만 있거나 맨 위에 있으면 카카오톡 버튼 클릭 시 휴대폰에서 localhost로 튕깁니다. 반드시 <code>https://taewook-3196.github.io</code>를 등록해 주세요!</span>
            </li><br>
            <li><b>토큰 발급 (Access & Refresh):</b><br>
                • <b>간이 테스트</b>: 상단 [도구] &gt; [REST API 테스트] &gt; 앱 선택 후 [토큰 발급]<br>
                • <b>영구 자동 갱신(강력 권장)</b>: 터미널에서 <code>python scripts/issue_kakao_tokens.py</code> 실행
            </li>
        </ol>
        <p style="color: #94a3b8; font-size: 12px; margin-top: 5px;">
            ※ 상세한 단계별 캡처 및 FAQ는 프로젝트 폴더의 <b>auto_kakaotalk_service.txt</b> 문서를 참조하세요.
        </p>
        """)
        layout.addWidget(guide_text)

        btn_box = QHBoxLayout()
        btn_open_kakao = QPushButton("🌐 카카오 개발자 사이트 열기")
        btn_open_kakao.setProperty("class", "secondary-btn")
        btn_open_kakao.clicked.connect(lambda: webbrowser.open("https://developers.kakao.com"))
        btn_box.addWidget(btn_open_kakao)

        btn_box.addStretch()

        btn_close = QPushButton("확인")
        btn_close.setProperty("class", "primary-btn")
        btn_close.setFixedWidth(80)
        btn_close.clicked.connect(self.accept)
        btn_box.addWidget(btn_close)

        layout.addLayout(btn_box)


class AccountDialog(QDialog):
    """계좌 등록 및 수정을 위한 모달 대화상자"""

    def __init__(self, account=None, parent=None):
        super().__init__(parent)
        self.account = account
        self.setWindowTitle("계좌 " + ("수정" if account else "추가"))
        self.setFixedWidth(460)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(10)

        self.input_name = QLineEdit(self.account.account_name if self.account else "")
        self.input_name.setPlaceholderText("예: 신한 IRP, 미래에셋 연금저축")
        form.addRow("계좌명 (필수):", self.input_name)

        self.input_broker = QLineEdit(self.account.broker if self.account else "")
        self.input_broker.setPlaceholderText("예: 신한투자증권, 미래에셋증권")
        form.addRow("증권사:", self.input_broker)

        self.input_number = QLineEdit(self.account.account_number if self.account else "")
        self.input_number.setPlaceholderText("예: 110-123-456789")
        form.addRow("계좌번호:", self.input_number)

        self.spin_capital = QSpinBox()
        self.spin_capital.setRange(0, 2000000000)
        self.spin_capital.setSingleStep(1000000)
        self.spin_capital.setValue(int(self.account.initial_capital) if self.account else 100000000)
        form.addRow("초기 한도 (원):", self.spin_capital)

        self.spin_base = QSpinBox()
        self.spin_base.setRange(0, 100000000)
        self.spin_base.setSingleStep(1000000)
        self.spin_base.setValue(int(self.account.base_monthly) if self.account else 10000000)
        form.addRow("월 예산 (원):", self.spin_base)

        self.spin_max_add = QSpinBox()
        self.spin_max_add.setRange(0, 100000000)
        self.spin_max_add.setSingleStep(1000000)
        self.spin_max_add.setValue(int(self.account.max_additional_monthly) if self.account else 3000000)
        form.addRow("추가 매수 한도 (원):", self.spin_max_add)

        # 투자 주기 선택
        self.combo_cycle_type = QComboBox()
        self.combo_cycle_type.addItem("매월 (특정 일)", "monthly")
        self.combo_cycle_type.addItem("매주 (특정 요일)", "weekly")
        self.combo_cycle_type.addItem("격주 (특정 요일)", "biweekly")
        self.combo_cycle_type.addItem("격월 (특정 일)", "bimonthly")
        self.combo_cycle_type.addItem("분기 (분기 특정 일)", "quarterly")
        self.combo_cycle_type.addItem("매일 (영업일 매수)", "daily")
        self.combo_cycle_type.addItem("투자 주기 없음 (수동 매수)", "none")

        cur_cycle_type = getattr(self.account, "buy_cycle_type", "monthly") if self.account else "monthly"
        for i in range(self.combo_cycle_type.count()):
            if self.combo_cycle_type.itemData(i) == cur_cycle_type:
                self.combo_cycle_type.setCurrentIndex(i)
                break

        form.addRow("매수 주기 구분:", self.combo_cycle_type)

        # 주기 세부 지정
        self.combo_cycle_detail = QComboBox()
        form.addRow("주기 세부 지정:", self.combo_cycle_detail)

        self.combo_cycle_type.currentIndexChanged.connect(self._on_cycle_type_changed)
        cur_cycle_detail = getattr(self.account, "buy_cycle_detail", "25") if self.account else "25"
        self._update_cycle_detail_items(cur_cycle_type, cur_cycle_detail)

        self.input_memo = QLineEdit(self.account.memo if self.account else "")
        form.addRow("메모:", self.input_memo)

        self.chk_default = QCheckBox("이 계좌를 기본 계좌로 지정")
        self.chk_default.setChecked(bool(self.account.is_default) if self.account else False)
        form.addRow("", self.chk_default)

        layout.addLayout(form)

        btn_box = QHBoxLayout()
        btn_box.addStretch()
        btn_save = QPushButton("저장")
        btn_save.setProperty("class", "primary-btn")
        btn_save.clicked.connect(self._validate_and_accept)
        btn_cancel = QPushButton("취소")
        btn_cancel.setProperty("class", "secondary-btn")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_save)
        btn_box.addWidget(btn_cancel)
        layout.addLayout(btn_box)

    def _on_cycle_type_changed(self):
        ctype = self.combo_cycle_type.currentData()
        self._update_cycle_detail_items(ctype, "25" if ctype in ("monthly", "bimonthly", "quarterly") else "TUE")

    def _update_cycle_detail_items(self, ctype: str, selected_val: str):
        self.combo_cycle_detail.blockSignals(True)
        self.combo_cycle_detail.clear()

        if ctype in ("weekly", "biweekly"):
            self.combo_cycle_detail.setEnabled(True)
            weekdays = [
                ("월요일", "MON"),
                ("화요일", "TUE"),
                ("수요일", "WED"),
                ("목요일", "THU"),
                ("금요일", "FRI"),
            ]
            for name, code in weekdays:
                self.combo_cycle_detail.addItem(name, code)
        elif ctype in ("monthly", "bimonthly", "quarterly"):
            self.combo_cycle_detail.setEnabled(True)
            for d in range(1, 29):
                self.combo_cycle_detail.addItem(f"{d}일", str(d))
            self.combo_cycle_detail.addItem("말일", "LAST")
        else:
            self.combo_cycle_detail.setEnabled(False)
            self.combo_cycle_detail.addItem("- (해당 없음)", "")

        for i in range(self.combo_cycle_detail.count()):
            if str(self.combo_cycle_detail.itemData(i)) == str(selected_val):
                self.combo_cycle_detail.setCurrentIndex(i)
                break

        self.combo_cycle_detail.blockSignals(False)

    def _validate_and_accept(self):
        if not self.input_name.text().strip():
            QMessageBox.warning(self, "입력 오류", "계좌명을 입력해주세요.")
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "account_name": self.input_name.text().strip(),
            "broker": self.input_broker.text().strip(),
            "account_number": self.input_number.text().strip(),
            "initial_capital": float(self.spin_capital.value()),
            "base_monthly": float(self.spin_base.value()),
            "max_additional_monthly": float(self.spin_max_add.value()),
            "buy_cycle_type": self.combo_cycle_type.currentData(),
            "buy_cycle_detail": self.combo_cycle_detail.currentData() or "",
            "is_default": 1 if self.chk_default.isChecked() else 0,
            "memo": self.input_memo.text().strip(),
        }


class SettingsPage(QWidget):
    settings_saved = Signal()

    def __init__(self, config: AppConfig, repo: Repository, parent=None):
        super().__init__(parent)
        self.config = config
        self.repo = repo
        self.current_selected_account_id: Optional[int] = None
        self._is_loading: bool = True
        self._user_edited_gemini_key: bool = False

        self._setup_ui()

    def _setup_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 탭 전체 스크롤 영역 (창 크기가 작아도 모든 설정 항목이 잘림 없이 표시됨)
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setObjectName("SettingsScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        content_widget = QWidget()
        content_widget.setObjectName("SettingsContentWidget")
        content_widget.setStyleSheet("#SettingsContentWidget { background: transparent; }")

        main_layout = QVBoxLayout(content_widget)
        main_layout.setContentsMargins(24, 20, 24, 24)
        main_layout.setSpacing(20)

        # 1. 계좌 관리 카드 (프리미엄 멀티 계좌 관리)
        acc_frame = QFrame()
        acc_frame.setProperty("class", "card")
        acc_layout = QVBoxLayout(acc_frame)

        acc_header = QHBoxLayout()
        acc_title = QLabel("계좌 관리 (Multi-Account)")
        acc_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #f8fafc;")
        acc_header.addWidget(acc_title)
        acc_header.addStretch()

        btn_acc_add = QPushButton("＋ 계좌 추가")
        btn_acc_add.setProperty("class", "primary-btn")
        btn_acc_add.clicked.connect(self._add_account)
        acc_header.addWidget(btn_acc_add)

        btn_acc_edit = QPushButton("✏️ 선택 수정")
        btn_acc_edit.setProperty("class", "secondary-btn")
        btn_acc_edit.clicked.connect(self._edit_account)
        acc_header.addWidget(btn_acc_edit)

        btn_acc_del = QPushButton("🗑️ 선택 삭제")
        btn_acc_del.setProperty("class", "danger-btn")
        btn_acc_del.clicked.connect(self._del_account)
        acc_header.addWidget(btn_acc_del)

        btn_acc_def = QPushButton("⭐ 기본계좌 지정")
        btn_acc_def.setProperty("class", "secondary-btn")
        btn_acc_def.clicked.connect(self._set_default_account)
        acc_header.addWidget(btn_acc_def)

        acc_layout.addLayout(acc_header)

        self.table_accounts = QTableWidget()
        acc_headers = [
            "ID", "계좌명", "증권사", "계좌번호",
            "초기 한도", "월 예산", "추가 매수", "매수 주기", "기본계좌"
        ]
        self.table_accounts.setColumnCount(len(acc_headers))
        self.table_accounts.setHorizontalHeaderLabels(acc_headers)
        h_acc = self.table_accounts.horizontalHeader()
        h_acc.setSectionsMovable(True)
        h_acc.setSectionResizeMode(QHeaderView.Interactive)
        self.table_accounts.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table_accounts.verticalHeader().setDefaultSectionSize(32)
        self.table_accounts.setMinimumHeight(130)
        self.table_accounts.setMaximumHeight(200)
        self.table_accounts.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_accounts.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_accounts.doubleClicked.connect(self._edit_account)
        self.table_accounts.itemSelectionChanged.connect(self._on_account_selection_changed)
        acc_layout.addWidget(self.table_accounts)

        main_layout.addWidget(acc_frame)

        # 2. 목표 비중 설정 테이블 카드 (계좌 관리 바로 다음 배치 & 선택 계좌와 실시간 연동)
        etf_frame = QFrame()
        etf_frame.setProperty("class", "card")
        etf_layout = QVBoxLayout(etf_frame)

        etf_header_box = QHBoxLayout()
        self.etf_title = QLabel("목표 비중 설정")
        self.etf_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #f8fafc;")
        etf_header_box.addWidget(self.etf_title)

        self.lbl_selected_acc_name = QLabel("")
        self.lbl_selected_acc_name.setStyleSheet(
            "font-size: 12px; font-weight: bold; color: #60a5fa; "
            "background-color: rgba(59, 130, 246, 0.15); "
            "border: 1px solid rgba(59, 130, 246, 0.35); "
            "border-radius: 4px; padding: 2px 8px;"
        )
        etf_header_box.addWidget(self.lbl_selected_acc_name)

        self.lbl_weight_sum = QLabel("목표 합계: 100.0%")
        self.lbl_weight_sum.setStyleSheet("font-weight: bold; color: #34d399;")
        etf_header_box.addWidget(self.lbl_weight_sum)
        etf_header_box.addStretch()

        btn_search = QPushButton("🔍 종목 검색 추가")
        btn_search.setProperty("class", "primary-btn")
        btn_search.clicked.connect(self._open_search_dialog)
        etf_header_box.addWidget(btn_search)

        btn_add = QPushButton("＋ 직접 입력")
        btn_add.setProperty("class", "secondary-btn")
        btn_add.clicked.connect(self._add_etf_row)
        etf_header_box.addWidget(btn_add)

        btn_del = QPushButton("－ 선택 삭제")
        btn_del.setProperty("class", "danger-btn")
        btn_del.clicked.connect(self._del_etf_row)
        etf_header_box.addWidget(btn_del)

        btn_save_target = QPushButton("💾 비중 즉시 적용")
        btn_save_target.setProperty("class", "secondary-btn")
        btn_save_target.clicked.connect(self._save_target_weights_only)
        etf_header_box.addWidget(btn_save_target)

        etf_layout.addLayout(etf_header_box)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["종목코드", "종목명", "목표비중 (%)"])
        header = self.table.horizontalHeader()
        header.setSectionsMovable(True)
        header.setDragEnabled(True)
        header.setFirstSectionMovable(True)
        header.setSectionResizeMode(QHeaderView.Interactive)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setMinimumHeight(160)
        self.table.setMaximumHeight(320)
        self.table.cellChanged.connect(self._on_table_cell_changed)
        etf_layout.addWidget(self.table)

        main_layout.addWidget(etf_frame)

        # 3. 기본 옵션 카드 (데이터 소스, 뉴스 전광판, 시작 인트로)
        opt_frame = QFrame()
        opt_frame.setProperty("class", "card")
        opt_layout = QVBoxLayout(opt_frame)

        opt_title = QLabel("기본 옵션")
        opt_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #f8fafc;")
        opt_layout.addWidget(opt_title)

        form = QFormLayout()
        form.setSpacing(12)
        form.setVerticalSpacing(14)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.combo_source = QComboBox()
        self.combo_source.setMinimumHeight(36)
        self.combo_source.addItem("네이버 금융 실시간 시세 (추천, 무설정)", "naver")
        self.combo_source.addItem("KRX 공식 Open API (키 연동)", "krx")
        self.combo_source.addItem("Mock 시뮬레이션 모의 데이터", "mock")
        idx = self.combo_source.findData(self.config.data_source)
        self.combo_source.setCurrentIndex(idx if idx >= 0 else 0)
        form.addRow("데이터 공급원 (Data Source):", self.combo_source)

        self.combo_news_mode = QComboBox()
        self.combo_news_mode.setMinimumHeight(36)
        self.combo_news_mode.addItem("모든 최신 경제 뉴스 (내 종목 + 구성종목 + 주요 경제속보)", "all")
        self.combo_news_mode.addItem("내가 등록한 종목 관련 뉴스만 (ETF 및 핵심 구성종목)", "portfolio_only")
        if getattr(self.config, "news_filter_mode", "all") == "portfolio_only":
            self.combo_news_mode.setCurrentIndex(1)
        form.addRow("하단 뉴스 전광판 표시 범위:", self.combo_news_mode)

        self.combo_splash = QComboBox()
        self.combo_splash.setMinimumHeight(36)
        self.combo_splash.addItem("표시 (황금돼지 인트로 애니메이션 표출)", True)
        self.combo_splash.addItem("끄기 (황금돼지 인트로 생략 및 즉시 시작)", False)
        if not getattr(self.config, "show_splash_screen", True):
            self.combo_splash.setCurrentIndex(1)
        form.addRow("시작 인트로 화면 (황금돼지):", self.combo_splash)

        opt_layout.addLayout(form)
        main_layout.addWidget(opt_frame)

        # 4. 모닝 모바일 웹 리포트 & 카카오톡 알림 카드
        m_frame = QFrame()
        m_frame.setProperty("class", "card")
        m_layout = QVBoxLayout(m_frame)
        m_layout.setSpacing(14)

        m_header = QHBoxLayout()
        m_title = QLabel("📱 모닝 모바일 웹 리포트 & 카카오톡 알림")
        m_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #f8fafc;")
        m_header.addWidget(m_title)
        m_header.addStretch()

        self.btn_kakao_guide = QPushButton("🔑 카카오톡 연동 가이드")
        self.btn_kakao_guide.setProperty("class", "secondary-btn")
        self.btn_kakao_guide.clicked.connect(self._open_kakao_guide)
        m_header.addWidget(self.btn_kakao_guide)
        m_layout.addLayout(m_header)

        m_desc = QLabel(
            "매일 아침 지정된 시간에 내 계좌 현황, 투자 가이드(AI 브리핑), 관심 종목 뉴스를 담은 모바일 웹 리포트와 카카오톡 요약 알림을 발송합니다."
        )
        m_desc.setStyleSheet("font-size: 12px; color: #94a3b8;")
        m_layout.addWidget(m_desc)

        m_form = QFormLayout()
        m_form.setSpacing(10)
        m_form.setVerticalSpacing(12)

        # 1) 기능 활성화
        self.chk_morning_enabled = QCheckBox("매일 아침 모바일 웹 리포트 생성 및 카카오톡 발송 활성화")
        self.chk_morning_enabled.setStyleSheet("font-weight: bold; color: #38bdf8;")
        m_form.addRow("기능 사용 여부:", self.chk_morning_enabled)

        # 2) 발송 시간 (기본 07:00)
        self.time_morning_send = QTimeEdit()
        self.time_morning_send.setDisplayFormat("HH:mm")
        self.time_morning_send.setTime(QTime(7, 0))
        self.time_morning_send.setFixedWidth(120)
        self.time_morning_send.setMinimumHeight(32)
        m_form.addRow("리포트 발송 시간:", self.time_morning_send)

        # 3) 카카오 REST API 키
        self.input_kakao_api_key = QLineEdit()
        self.input_kakao_api_key.setPlaceholderText("카카오 디벨로퍼스 REST API 키")
        self.input_kakao_api_key.setMinimumHeight(32)
        m_form.addRow("카카오 REST API 키:", self.input_kakao_api_key)

        # 4) 카카오 Access Token
        self.input_kakao_access = QLineEdit()
        self.input_kakao_access.setPlaceholderText("카카오 메시지 발송용 Access Token")
        self.input_kakao_access.setMinimumHeight(32)
        m_form.addRow("카카오 Access Token:", self.input_kakao_access)

        # 5) 카카오 Refresh Token
        self.input_kakao_refresh = QLineEdit()
        self.input_kakao_refresh.setPlaceholderText("토큰 자동 갱신용 Refresh Token (만료 방지)")
        self.input_kakao_refresh.setMinimumHeight(32)
        m_form.addRow("카카오 Refresh Token:", self.input_kakao_refresh)

        # 6) 리포트 포함 항목 선택 (체크박스 목록)
        box_items = QVBoxLayout()
        box_items.setSpacing(6)

        self.chk_inc_briefing = QCheckBox("🤖 내 계좌 투자 가이드 & AI 매수 브리핑 (D-day, 추천 매수액, 리밸런싱 조언)")
        self.chk_inc_briefing.setChecked(True)
        box_items.addWidget(self.chk_inc_briefing)

        self.chk_inc_news = QCheckBox("📰 관심 및 보유 종목 맞춤 시황 뉴스 (네이버 금융 & 구글 속보)")
        self.chk_inc_news.setChecked(True)
        box_items.addWidget(self.chk_inc_news)

        self.chk_inc_summary = QCheckBox("💰 계좌 자산 총괄 및 수익률 현황 (총평가, 원금, 손익, 예수금 KPI)")
        self.chk_inc_summary.setChecked(True)
        box_items.addWidget(self.chk_inc_summary)

        self.chk_inc_positions = QCheckBox("📊 보유 종목별 세부 현황표 (현재비중 vs 목표비중, 주수, 수익률)")
        self.chk_inc_positions.setChecked(True)
        box_items.addWidget(self.chk_inc_positions)

        self.chk_inc_market = QCheckBox("📈 주요 시장 지수 요약 (KODEX 200 등 주요 증시 지표)")
        self.chk_inc_market.setChecked(True)
        box_items.addWidget(self.chk_inc_market)

        m_form.addRow("리포트 포함 항목:", box_items)
        m_layout.addLayout(m_form)

        # 동작 버튼들
        m_btn_box = QHBoxLayout()
        self.btn_preview_report = QPushButton("🌐 웹 리포트 브라우저 미리보기")
        self.btn_preview_report.setProperty("class", "secondary-btn")
        self.btn_preview_report.clicked.connect(self._preview_morning_report)
        m_btn_box.addWidget(self.btn_preview_report)

        self.btn_test_kakao = QPushButton("🚀 테스트 리포트 생성 및 카톡 즉시 발송")
        self.btn_test_kakao.setProperty("class", "primary-btn")
        self.btn_test_kakao.clicked.connect(self._test_kakao_send)
        m_btn_box.addWidget(self.btn_test_kakao)

        m_btn_box.addStretch()
        m_layout.addLayout(m_btn_box)

        # 구분선 (Google Gemini AI 연동 영역)
        line_gemini = QFrame()
        line_gemini.setFrameShape(QFrame.HLine)
        line_gemini.setStyleSheet("border: none; border-top: 1px solid rgba(255, 255, 255, 0.1); margin: 10px 0;")
        m_layout.addWidget(line_gemini)

        # Gemini 헤더
        gemini_header = QHBoxLayout()
        gemini_title = QLabel("✨ Google Gemini AI 매크로 투자 가이드 설정")
        gemini_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #c084fc;")
        gemini_header.addWidget(gemini_title)
        gemini_header.addStretch()

        self.btn_gemini_key_link = QPushButton("🌐 Google AI Studio (무료 API 키 발급)")
        self.btn_gemini_key_link.setProperty("class", "secondary-btn")
        self.btn_gemini_key_link.clicked.connect(lambda: webbrowser.open("https://aistudio.google.com/"))
        gemini_header.addWidget(self.btn_gemini_key_link)
        m_layout.addLayout(gemini_header)

        gemini_desc = QLabel(
            "최신 Google Gemini 모델을 통해 환율, 글로벌 거시경제(매크로) 시황과 결합된 전문적인 AI 모닝 투자 조언을 생성합니다."
        )
        gemini_desc.setStyleSheet("font-size: 12px; color: #94a3b8;")
        m_layout.addWidget(gemini_desc)

        gemini_form = QFormLayout()
        gemini_form.setSpacing(10)

        # 1) Gemini 활성화 체크박스
        self.chk_gemini_enabled = QCheckBox("Google Gemini AI 거시경제(매크로) & 투자 가이드 분석 활성화")
        self.chk_gemini_enabled.setStyleSheet("font-weight: bold; color: #c084fc;")
        gemini_form.addRow("AI 분석 사용 여부:", self.chk_gemini_enabled)

        # 2) Gemini 모델 선택 콤보박스 (Editable)
        self.combo_gemini_model = QComboBox()
        self.combo_gemini_model.setEditable(True)
        self.combo_gemini_model.addItems([
            "gemini-3.8-flash",
            "gemini-3.6-flash",
            "gemini-3.7-flash",
        ])
        self.combo_gemini_model.setMinimumHeight(32)
        gemini_form.addRow("Gemini AI 모델:", self.combo_gemini_model)

        # 3) Gemini API Key 입력 (Password 모드 + 보기 토글)
        gemini_key_layout = QHBoxLayout()
        self.input_gemini_key = QLineEdit()
        self.input_gemini_key.setPlaceholderText("Google AI Studio 발급 API 키 (AIzaSy...)")
        self.input_gemini_key.setEchoMode(QLineEdit.Password)
        self.input_gemini_key.setMinimumHeight(32)
        gemini_key_layout.addWidget(self.input_gemini_key)

        self.btn_toggle_gemini_key = QPushButton("👁️")
        self.btn_toggle_gemini_key.setFixedWidth(36)
        self.btn_toggle_gemini_key.setToolTip("API 키 보기/숨기기")
        self.btn_toggle_gemini_key.clicked.connect(self._toggle_gemini_key_echo)
        gemini_key_layout.addWidget(self.btn_toggle_gemini_key)

        gemini_form.addRow("Gemini API Key:", gemini_key_layout)

        # 4) AI 투자 조언 방향성 (투자 성향 5단계) 슬라이더
        stance_container = QWidget()
        stance_layout = QVBoxLayout(stance_container)
        stance_layout.setContentsMargins(0, 4, 0, 4)
        stance_layout.setSpacing(6)

        self.slider_investment_stance = QSlider(Qt.Horizontal)
        self.slider_investment_stance.setRange(0, 4)
        self.slider_investment_stance.setSingleStep(1)
        self.slider_investment_stance.setPageStep(1)
        self.slider_investment_stance.setTickPosition(QSlider.TicksBelow)
        self.slider_investment_stance.setTickInterval(1)
        self.slider_investment_stance.setValue(2)  # 기본값: 2 (중립/균형)
        self.slider_investment_stance.setMinimumHeight(28)
        self.slider_investment_stance.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 8px;
                background: rgba(255, 255, 255, 0.12);
                border-radius: 4px;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #38bdf8, stop:0.5 #c084fc, stop:1 #f43f5e);
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                border: 2px solid #c084fc;
                width: 20px;
                margin-top: -6px;
                margin-bottom: -6px;
                border-radius: 10px;
            }
            QSlider::handle:horizontal:hover {
                background: #c084fc;
                border: 2px solid #ffffff;
            }
        """)

        # 5개 눈금 라벨 레이아웃
        ticks_layout = QHBoxLayout()
        ticks_labels = ["🛡️ 매우 보수적", "보수적", "⚖️ 중립/균형", "공격적", "🔥 매우 공격적"]
        for i, text in enumerate(ticks_labels):
            t_lbl = QLabel(text)
            if i == 0:
                t_lbl.setAlignment(Qt.AlignLeft)
                t_lbl.setStyleSheet("font-size: 11px; color: #38bdf8; font-weight: 600;")
            elif i == 4:
                t_lbl.setAlignment(Qt.AlignRight)
                t_lbl.setStyleSheet("font-size: 11px; color: #f43f5e; font-weight: 600;")
            elif i == 2:
                t_lbl.setAlignment(Qt.AlignCenter)
                t_lbl.setStyleSheet("font-size: 11px; color: #c084fc; font-weight: 600;")
            else:
                t_lbl.setAlignment(Qt.AlignCenter)
                t_lbl.setStyleSheet("font-size: 11px; color: #94a3b8;")
            ticks_layout.addWidget(t_lbl)

        # 동적 상세 설명 카드
        self.card_stance_info = QFrame()
        self.card_stance_info.setStyleSheet("""
            QFrame {
                background: rgba(192, 132, 252, 0.08);
                border: 1px solid rgba(192, 132, 252, 0.25);
                border-radius: 8px;
            }
        """)
        card_layout = QVBoxLayout(self.card_stance_info)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(4)

        self.lbl_stance_title = QLabel("⚖️ 중립/균형 (정석 퀀트 자산배분)")
        self.lbl_stance_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #e9d5ff;")
        card_layout.addWidget(self.lbl_stance_title)

        self.lbl_stance_desc = QLabel(
            "정석 퀀트 자산배분. 매크로 지표를 객관적으로 분석하고 정해진 주기 및 목표 비중 괴리도 공식에 따라 기계적 분할 매수 원칙을 준수합니다."
        )
        self.lbl_stance_desc.setStyleSheet("font-size: 12px; color: #cbd5e1; line-height: 1.4;")
        self.lbl_stance_desc.setWordWrap(True)
        card_layout.addWidget(self.lbl_stance_desc)

        stance_layout.addWidget(self.slider_investment_stance)
        stance_layout.addLayout(ticks_layout)
        stance_layout.addWidget(self.card_stance_info)

        gemini_form.addRow("투자 조언 방향성:", stance_container)
        m_layout.addLayout(gemini_form)

        # 5) Gemini 연결 테스트 및 저장 버튼
        gemini_btn_box = QHBoxLayout()
        self.btn_test_gemini = QPushButton("🧪 Gemini AI 연결 및 테스트")
        self.btn_test_gemini.setProperty("class", "secondary-btn")
        self.btn_test_gemini.clicked.connect(self._test_gemini_connection)
        gemini_btn_box.addWidget(self.btn_test_gemini)

        self.btn_save_gemini = QPushButton("💾 Gemini 설정 저장")
        self.btn_save_gemini.setProperty("class", "primary-btn")
        self.btn_save_gemini.clicked.connect(self._save_gemini_settings_manually)
        gemini_btn_box.addWidget(self.btn_save_gemini)

        self.lbl_gemini_test_result = QLabel("")
        self.lbl_gemini_test_result.setStyleSheet("font-size: 12px; color: #38bdf8;")
        gemini_btn_box.addWidget(self.lbl_gemini_test_result)
        gemini_btn_box.addStretch()
        m_layout.addLayout(gemini_btn_box)

        # 자동 저장 및 슬라이더 이벤트 연결
        self.input_gemini_key.textEdited.connect(self._on_gemini_key_text_edited)
        self.input_gemini_key.editingFinished.connect(self._auto_save_morning_report_settings)
        self.combo_gemini_model.currentTextChanged.connect(self._auto_save_morning_report_settings)
        self.chk_gemini_enabled.toggled.connect(self._auto_save_morning_report_settings)
        self.slider_investment_stance.valueChanged.connect(self._on_stance_slider_changed)

        # 구분선 (클라우드 원격 제어 영역)
        line_cloud = QFrame()
        line_cloud.setFrameShape(QFrame.HLine)
        line_cloud.setStyleSheet("border: none; border-top: 1px solid rgba(255, 255, 255, 0.1); margin: 10px 0;")
        m_layout.addWidget(line_cloud)

        # 클라우드 헤더
        cloud_header = QHBoxLayout()
        cloud_title = QLabel("☁️ GitHub 클라우드 자동 발송 원격 제어 (PC 꺼짐 대응)")
        cloud_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #38bdf8;")
        cloud_header.addWidget(cloud_title)
        cloud_header.addStretch()

        self.btn_gh_guide = QPushButton("🔑 GitHub 연동 가이드")
        self.btn_gh_guide.setProperty("class", "secondary-btn")
        self.btn_gh_guide.clicked.connect(self._open_github_guide)
        cloud_header.addWidget(self.btn_gh_guide)
        m_layout.addLayout(cloud_header)

        cloud_desc = QLabel(
            "PC가 꺼져 있어도 GitHub 클라우드 서버가 매일 아침 07:00에 카카오톡과 모바일 웹 리포트를 발송하도록 원격으로 켜거나 끌 수 있습니다."
        )
        cloud_desc.setStyleSheet("font-size: 12px; color: #94a3b8;")
        m_layout.addWidget(cloud_desc)

        cloud_form = QFormLayout()
        cloud_form.setSpacing(10)

        self.input_gh_repo = QLineEdit()
        self.input_gh_repo.setPlaceholderText("예: 내아이디/RetirementPortfolio")
        self.input_gh_repo.setMinimumHeight(32)
        cloud_form.addRow("GitHub 저장소 (owner/repo):", self.input_gh_repo)

        self.input_gh_token = QLineEdit()
        self.input_gh_token.setPlaceholderText("GitHub Personal Access Token (ghp_...)")
        self.input_gh_token.setEchoMode(QLineEdit.Password)
        self.input_gh_token.setMinimumHeight(32)
        cloud_form.addRow("GitHub 토큰 (PAT):", self.input_gh_token)

        # 상태 배지 & 새로고침 & On/Off 스위치
        cloud_status_box = QHBoxLayout()
        self.lbl_cloud_status = QLabel("⚪ 상태 확인 대기 중")
        self.lbl_cloud_status.setStyleSheet("font-weight: bold; color: #cbd5e1; padding: 4px 8px; background: rgba(255,255,255,0.05); border-radius: 4px;")
        cloud_status_box.addWidget(self.lbl_cloud_status)

        self.btn_cloud_refresh = QPushButton("🔄 상태 조회")
        self.btn_cloud_refresh.setProperty("class", "secondary-btn")
        self.btn_cloud_refresh.clicked.connect(self._check_cloud_status)
        cloud_status_box.addWidget(self.btn_cloud_refresh)

        self.btn_cloud_enable = QPushButton("🟢 클라우드 켜기 (ON)")
        self.btn_cloud_enable.setProperty("class", "primary-btn")
        self.btn_cloud_enable.clicked.connect(self._enable_cloud)
        cloud_status_box.addWidget(self.btn_cloud_enable)

        self.btn_cloud_disable = QPushButton("⚪ 클라우드 끄기 (OFF)")
        self.btn_cloud_disable.setProperty("class", "danger-btn")
        self.btn_cloud_disable.clicked.connect(self._disable_cloud)
        cloud_status_box.addWidget(self.btn_cloud_disable)

        self.btn_cloud_dispatch = QPushButton("🚀 클라우드 즉시 테스트 실행")
        self.btn_cloud_dispatch.setProperty("class", "secondary-btn")
        self.btn_cloud_dispatch.clicked.connect(self._trigger_cloud_now)
        cloud_status_box.addWidget(self.btn_cloud_dispatch)

        cloud_status_box.addStretch()
        cloud_form.addRow("클라우드 제어:", cloud_status_box)

        m_layout.addLayout(cloud_form)

        # 모닝 리포트/카카오/깃허브/Gemini 필드 자동 저장 연결 (입력 종료 시 즉시 영구 반영)
        self.input_kakao_api_key.editingFinished.connect(self._auto_save_morning_report_settings)
        self.input_kakao_access.editingFinished.connect(self._auto_save_morning_report_settings)
        self.input_kakao_refresh.editingFinished.connect(self._auto_save_morning_report_settings)
        self.chk_morning_enabled.toggled.connect(self._auto_save_morning_report_settings)
        self.time_morning_send.timeChanged.connect(self._auto_save_morning_report_settings)
        self.chk_inc_briefing.toggled.connect(self._auto_save_morning_report_settings)
        self.chk_inc_news.toggled.connect(self._auto_save_morning_report_settings)
        self.chk_inc_summary.toggled.connect(self._auto_save_morning_report_settings)
        self.chk_inc_positions.toggled.connect(self._auto_save_morning_report_settings)
        self.chk_inc_market.toggled.connect(self._auto_save_morning_report_settings)
        self.input_gh_repo.editingFinished.connect(self._auto_save_morning_report_settings)
        self.input_gh_token.editingFinished.connect(self._auto_save_morning_report_settings)

        main_layout.addWidget(m_frame)

        # 5. 설정 저장 버튼
        btn_save = QPushButton("💾 설정 저장하기")
        btn_save.setProperty("class", "primary-btn")
        btn_save.setFixedHeight(42)
        btn_save.setStyleSheet("font-size: 14px; font-weight: bold;")
        btn_save.clicked.connect(self._save_settings)
        main_layout.addWidget(btn_save)

        # 5. 데이터베이스 백업 및 복원 관리 카드 (프롬프트 13, 14번)
        db_frame = QFrame()
        db_frame.setProperty("class", "card")
        db_layout = QVBoxLayout(db_frame)

        db_title = QLabel("데이터베이스(SQLite) 백업 및 복원")
        db_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #f8fafc;")
        db_layout.addWidget(db_title)

        db_desc = QLabel(
            "SQLite Native Backup API를 통해 거래내역과 가격 데이터를 안전하게 단일 백업 파일로 보관합니다."
        )
        db_desc.setStyleSheet("font-size: 12px; color: #94a3b8;")
        db_layout.addWidget(db_desc)

        db_btn_box = QHBoxLayout()
        btn_backup = QPushButton("📦 데이터베이스 백업 생성")
        btn_backup.setProperty("class", "secondary-btn")
        btn_backup.clicked.connect(self._backup_db)
        db_btn_box.addWidget(btn_backup)

        btn_restore = QPushButton("🔄 백업 파일로 복원")
        btn_restore.setProperty("class", "secondary-btn")
        btn_restore.clicked.connect(self._restore_db)
        db_btn_box.addWidget(btn_restore)

        db_btn_box.addStretch()
        db_layout.addLayout(db_btn_box)

        main_layout.addWidget(db_frame)
        main_layout.addStretch()

        self.scroll_area.setWidget(content_widget)
        root_layout.addWidget(self.scroll_area)

        self.refresh()

    def refresh(self):
        self._is_loading = True
        try:
            self._refresh_accounts_table()
            if hasattr(self, "combo_source"):
                idx = self.combo_source.findData(self.config.data_source)
                self.combo_source.setCurrentIndex(idx if idx >= 0 else 0)
            if hasattr(self, "combo_news_mode"):
                self.combo_news_mode.setCurrentIndex(1 if getattr(self.config, "news_filter_mode", "all") == "portfolio_only" else 0)
            if hasattr(self, "combo_splash"):
                self.combo_splash.setCurrentIndex(0 if getattr(self.config, "show_splash_screen", True) else 1)

            # 모닝 리포트 설정 위젯 동기화
            m_cfg = getattr(self.config, "morning_report", MorningReportConfig())
            if hasattr(self, "chk_morning_enabled"):
                self.chk_morning_enabled.setChecked(bool(m_cfg.enabled))
            if hasattr(self, "time_morning_send"):
                try:
                    parts = m_cfg.send_time.split(":")
                    h, m = int(parts[0]), int(parts[1])
                    self.time_morning_send.setTime(QTime(h, m))
                except Exception:
                    self.time_morning_send.setTime(QTime(7, 0))
            if hasattr(self, "input_kakao_api_key"):
                self.input_kakao_api_key.setText(m_cfg.kakao_rest_api_key)
            if hasattr(self, "input_kakao_access"):
                self.input_kakao_access.setText(m_cfg.kakao_access_token)
            if hasattr(self, "input_kakao_refresh"):
                self.input_kakao_refresh.setText(m_cfg.kakao_refresh_token)
            if hasattr(self, "chk_inc_briefing"):
                self.chk_inc_briefing.setChecked(m_cfg.include_ai_briefing)
            if hasattr(self, "chk_inc_news"):
                self.chk_inc_news.setChecked(m_cfg.include_news)
            if hasattr(self, "chk_inc_summary"):
                self.chk_inc_summary.setChecked(m_cfg.include_summary)
            if hasattr(self, "chk_inc_positions"):
                self.chk_inc_positions.setChecked(m_cfg.include_positions)
            if hasattr(self, "chk_inc_market"):
                self.chk_inc_market.setChecked(m_cfg.include_market_indices)
            if hasattr(self, "input_gh_repo"):
                self.input_gh_repo.setText(m_cfg.github_repo)
            if hasattr(self, "input_gh_token"):
                self.input_gh_token.setText(m_cfg.github_token)
            if hasattr(self, "lbl_cloud_status"):
                if m_cfg.github_cloud_enabled:
                    self.lbl_cloud_status.setText("🟢 클라우드 활성화됨 (07:00 발송 대기)")
                    self.lbl_cloud_status.setStyleSheet("font-weight: bold; color: #34d399; padding: 4px 8px; background: rgba(16,185,129,0.15); border-radius: 4px;")
                else:
                    self.lbl_cloud_status.setText("⚪ 클라우드 비활성화됨 (중지 상태)")
                    self.lbl_cloud_status.setStyleSheet("font-weight: bold; color: #94a3b8; padding: 4px 8px; background: rgba(255,255,255,0.05); border-radius: 4px;")
            if hasattr(self, "chk_gemini_enabled"):
                self.chk_gemini_enabled.setChecked(getattr(m_cfg, "gemini_enabled", True))
            if hasattr(self, "input_gemini_key"):
                current_gemini_key = getattr(m_cfg, "gemini_api_key", "") or os.getenv("GEMINI_API_KEY", "")
                self.input_gemini_key.setText(current_gemini_key)
                if not getattr(m_cfg, "gemini_api_key", "") and current_gemini_key:
                    m_cfg.gemini_api_key = current_gemini_key
                self._user_edited_gemini_key = False
            if hasattr(self, "combo_gemini_model"):
                model_val = getattr(m_cfg, "gemini_model", "gemini-3.8-flash")
                idx = self.combo_gemini_model.findText(model_val)
                if idx >= 0:
                    self.combo_gemini_model.setCurrentIndex(idx)
                else:
                    self.combo_gemini_model.setCurrentText(model_val)
            if hasattr(self, "slider_investment_stance"):
                stance_val = getattr(m_cfg, "ai_investment_stance", "balanced")
                idx = STANCE_KEYS.index(stance_val) if stance_val in STANCE_KEYS else 2
                self.slider_investment_stance.setValue(idx)
                self._update_stance_display(idx)
        finally:
            self._is_loading = False

    def _refresh_accounts_table(self):
        accs = self.repo.get_accounts()
        self.table_accounts.blockSignals(True)
        self.table_accounts.setRowCount(len(accs))
        
        target_row = 0
        def_acc_id = None
        for row, a in enumerate(accs):
            if a.is_default:
                def_acc_id = a.id
            if self.current_selected_account_id is not None and a.id == self.current_selected_account_id:
                target_row = row

            self.table_accounts.setItem(row, 0, QTableWidgetItem(str(a.id)))
            self.table_accounts.setItem(row, 1, QTableWidgetItem(a.account_name))
            self.table_accounts.setItem(row, 2, QTableWidgetItem(a.broker or ""))
            self.table_accounts.setItem(row, 3, QTableWidgetItem(a.account_number or ""))
            self.table_accounts.setItem(row, 4, QTableWidgetItem(f"{a.initial_capital:,.0f}원"))
            self.table_accounts.setItem(row, 5, QTableWidgetItem(f"{a.base_monthly:,.0f}원"))
            self.table_accounts.setItem(row, 6, QTableWidgetItem(f"{a.max_additional_monthly:,.0f}원"))

            cycle_desc = format_cycle_description(getattr(a, "buy_cycle_type", "monthly"), getattr(a, "buy_cycle_detail", "25"))
            self.table_accounts.setItem(row, 7, QTableWidgetItem(cycle_desc))

            def_item = QTableWidgetItem("⭐ 기본" if a.is_default else "-")
            if a.is_default:
                def_item.setForeground(Qt.yellow)
            self.table_accounts.setItem(row, 8, def_item)

        self.table_accounts.blockSignals(False)
        self.table_accounts.resizeColumnsToContents()
        for col in range(self.table_accounts.columnCount()):
            cur_w = self.table_accounts.columnWidth(col)
            if col == 1:
                self.table_accounts.setColumnWidth(col, max(cur_w + 10, 140))
            elif col == 7:
                self.table_accounts.setColumnWidth(col, max(cur_w + 10, 130))
            else:
                self.table_accounts.setColumnWidth(col, cur_w + 8)

        if accs:
            if self.current_selected_account_id is None:
                self.current_selected_account_id = def_acc_id if def_acc_id is not None else accs[0].id
                target_row = 0
                for r, a in enumerate(accs):
                    if a.id == self.current_selected_account_id:
                        target_row = r
                        break

            self.table_accounts.blockSignals(True)
            self.table_accounts.selectRow(target_row)
            self.table_accounts.blockSignals(False)
            self._load_account_targets(self.current_selected_account_id)

    def _on_account_selection_changed(self):
        sel = self.table_accounts.selectionModel().selectedRows()
        if not sel:
            return
        row = sel[0].row()
        item = self.table_accounts.item(row, 0)
        if not item:
            return
        try:
            acc_id = int(item.text())
        except ValueError:
            return

        if self.current_selected_account_id == acc_id:
            return

        # 이전 계좌의 편집 내용을 검증 후 안전하게 저장
        if self.current_selected_account_id is not None:
            self._save_table_to_account_targets(self.current_selected_account_id)

        self.current_selected_account_id = acc_id
        self._load_account_targets(acc_id)

    def _load_account_targets(self, account_id: int):
        acc = self.repo.get_account(account_id)
        acc_name = acc.account_name if acc else f"계좌 {account_id}"
        self.lbl_selected_acc_name.setText(f"계좌: {acc_name}")

        targets = self.repo.get_account_targets(account_id)
        self.table.blockSignals(True)
        self.table.setRowCount(len(targets))
        for row, etf in enumerate(targets):
            self.table.setItem(row, 0, QTableWidgetItem(etf.ticker))
            self.table.setItem(row, 1, QTableWidgetItem(etf.name))
            self.table.setItem(row, 2, QTableWidgetItem(f"{etf.target_weight * 100:.1f}"))
        self.table.blockSignals(False)
        self._adjust_columns()
        self._on_table_cell_changed()

    def _extract_table_targets(self) -> tuple[bool, str, list[ETFConfig], float]:
        """현재 표의 목표 비중 데이터를 파싱 및 유효성을 검증합니다."""
        targets = []
        total_w = 0.0
        for row in range(self.table.rowCount()):
            c_item = self.table.item(row, 0)
            n_item = self.table.item(row, 1)
            w_item = self.table.item(row, 2)

            ticker = c_item.text().strip() if c_item else ""
            name = n_item.text().strip() if n_item else ""
            try:
                w_pct = float(w_item.text().replace("%", "").strip()) if w_item else 0.0
            except ValueError:
                return False, f"올바르지 않은 목표비중 값입니다 (행 {row + 1})", [], 0.0

            if not ticker:
                return False, f"종목코드는 빈 값일 수 없습니다 (행 {row + 1}).", [], 0.0

            target_weight = round(w_pct / 100.0, 4)
            total_w += target_weight
            targets.append(ETFConfig(ticker=ticker, name=name, target_weight=target_weight))

        if total_w > 1.0001:
            return False, f"목표 비중의 합계는 100%를 초과할 수 없습니다. (현재: {round(total_w * 100, 1)}%)", [], total_w

        return True, "", targets, total_w

    def _save_table_to_account_targets(self, account_id: int):
        valid, _, targets, _ = self._extract_table_targets()
        if valid and targets:
            self.repo.save_account_targets(account_id, targets)
            def_acc = self.repo.get_default_account()
            if def_acc and def_acc.id == account_id:
                self.config.etfs = targets

    def _save_target_weights_only(self):
        if self.current_selected_account_id is None:
            return
        valid, err_msg, targets, _ = self._extract_table_targets()
        if not valid:
            QMessageBox.critical(self, "오류", err_msg)
            return

        self.repo.save_account_targets(self.current_selected_account_id, targets)
        def_acc = self.repo.get_default_account()
        if def_acc and def_acc.id == self.current_selected_account_id:
            self.config.etfs = targets
            save_config(self.config)

        acc = self.repo.get_account(self.current_selected_account_id)
        acc_name = acc.account_name if acc else ""
        QMessageBox.information(self, "저장 완료", f"[{acc_name}] 계좌의 목표 비중 설정이 저장되었습니다.")
        self.settings_saved.emit()

    def _add_account(self):
        dlg = AccountDialog(parent=self)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            try:
                new_acc = self.repo.create_account(
                    account_name=data["account_name"],
                    account_number=data["account_number"],
                    broker=data["broker"],
                    initial_capital=data["initial_capital"],
                    base_monthly=data["base_monthly"],
                    max_additional_monthly=data["max_additional_monthly"],
                    buy_cycle_type=data["buy_cycle_type"],
                    buy_cycle_detail=data["buy_cycle_detail"],
                    is_default=data["is_default"],
                    memo=data["memo"],
                )
                self.current_selected_account_id = new_acc.id
                self._refresh_accounts_table()
                self.settings_saved.emit()
            except Exception as e:
                QMessageBox.critical(self, "계좌 등록 실패", f"계좌 등록 중 오류가 발생했습니다:\n{e}")

    def _edit_account(self):
        sel = self.table_accounts.selectionModel().selectedRows()
        if not sel:
            QMessageBox.information(self, "안내", "수정할 계좌 행을 선택해주세요.")
            return
        row = sel[0].row()
        acc_id = int(self.table_accounts.item(row, 0).text())
        acc = self.repo.get_account(acc_id)
        if not acc:
            return

        dlg = AccountDialog(account=acc, parent=self)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            try:
                self.repo.update_account(
                    account_id=acc_id,
                    account_name=data["account_name"],
                    account_number=data["account_number"],
                    broker=data["broker"],
                    initial_capital=data["initial_capital"],
                    base_monthly=data["base_monthly"],
                    max_additional_monthly=data["max_additional_monthly"],
                    buy_cycle_type=data["buy_cycle_type"],
                    buy_cycle_detail=data["buy_cycle_detail"],
                    is_default=data["is_default"],
                    memo=data["memo"],
                )
                self.current_selected_account_id = acc_id
                self._refresh_accounts_table()
                self.settings_saved.emit()
            except Exception as e:
                QMessageBox.critical(self, "계좌 수정 실패", f"계좌 수정 중 오류가 발생했습니다:\n{e}")

    def _del_account(self):
        sel = self.table_accounts.selectionModel().selectedRows()
        if not sel:
            QMessageBox.information(self, "안내", "삭제할 계좌 행을 선택해주세요.")
            return
        row = sel[0].row()
        acc_id = int(self.table_accounts.item(row, 0).text())
        acc_name = self.table_accounts.item(row, 1).text()

        accs = self.repo.get_accounts()
        if len(accs) <= 1:
            QMessageBox.warning(self, "삭제 불가", "최소 1개의 계좌는 등록되어 있어야 합니다.")
            return

        reply = QMessageBox.question(
            self,
            "계좌 삭제 확인",
            f"계좌 [{acc_name}] (ID: {acc_id})를 정말 삭제하시겠습니까?\n이 계좌에 속한 거래는 계좌 연결이 해제됩니다.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            if self.current_selected_account_id == acc_id:
                self.current_selected_account_id = None
            self.repo.delete_account(acc_id)
            self._refresh_accounts_table()
            self.settings_saved.emit()

    def _set_default_account(self):
        sel = self.table_accounts.selectionModel().selectedRows()
        if not sel:
            QMessageBox.information(self, "안내", "기본 계좌로 지정할 계좌 행을 선택해주세요.")
            return
        row = sel[0].row()
        acc_id = int(self.table_accounts.item(row, 0).text())
        self.repo.set_default_account(acc_id)
        self.current_selected_account_id = acc_id
        self._refresh_accounts_table()
        self.settings_saved.emit()

    def _adjust_columns(self):
        self.table.resizeColumnsToContents()
        for col in range(self.table.columnCount()):
            cur_w = self.table.columnWidth(col)
            if col == 1:
                self.table.setColumnWidth(col, max(cur_w + 10, 180))
            else:
                self.table.setColumnWidth(col, cur_w + 8)

    def _on_table_cell_changed(self):
        total_w = 0.0
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 2)
            if item:
                try:
                    total_w += float(item.text().replace("%", "").strip())
                except ValueError:
                    pass

        if total_w <= 100.0001:
            cash_w = max(0.0, 100.0 - total_w)
            if cash_w > 0.001:
                self.lbl_weight_sum.setText(f"목표 합계: {total_w:.1f}% (현금: {cash_w:.1f}%)")
            else:
                self.lbl_weight_sum.setText(f"목표 합계: {total_w:.1f}%")
            self.lbl_weight_sum.setStyleSheet("font-weight: bold; color: #34d399;")
        else:
            self.lbl_weight_sum.setText(f"목표 합계: {total_w:.1f}% (100% 초과!)")
            self.lbl_weight_sum.setStyleSheet("font-weight: bold; color: #f87171;")

    def _open_search_dialog(self):
        from ui.widgets.etf_search_dialog import ETFSearchDialog
        dlg = ETFSearchDialog(self.repo, self)
        if dlg.exec() == QDialog.Accepted and dlg.selected_item:
            ticker, name = dlg.selected_item
            for r in range(self.table.rowCount()):
                item = self.table.item(r, 0)
                if item and item.text().strip() == ticker:
                    QMessageBox.warning(self, "안내", f"이미 등록된 종목입니다: {name} ({ticker})")
                    return
            row = self.table.rowCount()
            self.table.blockSignals(True)
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(ticker))
            self.table.setItem(row, 1, QTableWidgetItem(name))
            self.table.setItem(row, 2, QTableWidgetItem("0.0"))
            self.table.blockSignals(False)
            self._adjust_columns()
            self.table.selectRow(row)
            self._on_table_cell_changed()

    def _add_etf_row(self):
        row = self.table.rowCount()
        self.table.blockSignals(True)
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(""))
        self.table.setItem(row, 1, QTableWidgetItem(""))
        self.table.setItem(row, 2, QTableWidgetItem("0.0"))
        self.table.blockSignals(False)
        self._adjust_columns()
        self.table.setCurrentCell(row, 0)
        self.table.editItem(self.table.item(row, 0))
        self._on_table_cell_changed()

    def _del_etf_row(self):
        current_row = self.table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "안내", "삭제할 종목 행을 먼저 표에서 선택해주세요.")
            return
        self.table.removeRow(current_row)
        self._on_table_cell_changed()

    def _save_settings(self):
        valid, err_msg, new_etfs, total_w = self._extract_table_targets()
        if not valid:
            QMessageBox.critical(self, "오류", err_msg)
            return

        if self.current_selected_account_id is not None:
            self.repo.save_account_targets(self.current_selected_account_id, new_etfs)
            def_acc = self.repo.get_default_account()
            if def_acc and def_acc.id == self.current_selected_account_id:
                self.config.etfs = new_etfs
        else:
            self.config.etfs = new_etfs

        def_acc = self.repo.get_default_account()
        if def_acc:
            self.config.initial_capital = int(def_acc.initial_capital)
            self.config.base_monthly = int(def_acc.base_monthly)
            self.config.max_additional_monthly = int(def_acc.max_additional_monthly)
        self.config.data_source = self.combo_source.currentData()
        self.config.news_filter_mode = self.combo_news_mode.currentData()
        self.config.show_splash_screen = bool(self.combo_splash.currentData())

        # 모닝 리포트 설정 동기화
        self._sync_morning_report_from_ui()

        try:
            save_config(self.config)
            gemini_key = self.input_gemini_key.text().strip()
            if gemini_key:
                self._persist_to_env("GEMINI_API_KEY", gemini_key)
            QMessageBox.information(self, "저장 완료", "설정이 성공적으로 저장되었습니다.")
            self.settings_saved.emit()
        except Exception as e:
            QMessageBox.critical(self, "오류", f"설정 저장 실패: {e}")

    def _on_gemini_key_text_edited(self, text: str):
        self._user_edited_gemini_key = True

    def _persist_to_env(self, key_name: str, value: str):
        try:
            from core.paths import get_project_root
            env_file = get_project_root() / ".env"
            lines = []
            found = False
            if env_file.exists():
                with open(env_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip().startswith(f"{key_name}="):
                            lines.append(f"{key_name}={value}\n")
                            found = True
                        else:
                            lines.append(line)
            if not found:
                lines.append(f"{key_name}={value}\n")
            with open(env_file, "w", encoding="utf-8") as f:
                f.writelines(lines)
            os.environ[key_name] = value
        except Exception as e:
            logger.debug(f".env 저장 실패 (무시 가능): {e}")

    def _sync_morning_report_from_ui(self):
        if getattr(self, "_is_loading", False):
            return
        m_cfg = getattr(self.config, "morning_report", MorningReportConfig())
        m_cfg.enabled = self.chk_morning_enabled.isChecked()
        m_cfg.send_time = self.time_morning_send.time().toString("HH:mm")
        k_rest = self.input_kakao_api_key.text().strip()
        if k_rest or not m_cfg.kakao_rest_api_key:
            m_cfg.kakao_rest_api_key = k_rest

        k_acc = self.input_kakao_access.text().strip()
        if k_acc or not m_cfg.kakao_access_token:
            m_cfg.kakao_access_token = k_acc

        k_ref = self.input_kakao_refresh.text().strip()
        if k_ref or not m_cfg.kakao_refresh_token:
            m_cfg.kakao_refresh_token = k_ref

        m_cfg.include_ai_briefing = self.chk_inc_briefing.isChecked()
        m_cfg.include_news = self.chk_inc_news.isChecked()
        m_cfg.include_summary = self.chk_inc_summary.isChecked()
        m_cfg.include_positions = self.chk_inc_positions.isChecked()
        m_cfg.include_market_indices = self.chk_inc_market.isChecked()
        if hasattr(self, "input_gh_repo"):
            repo_text = self.input_gh_repo.text().strip()
            if "github.com/" in repo_text:
                repo_text = repo_text.split("github.com/")[1].strip("/").removesuffix(".git")
            if repo_text or not m_cfg.github_repo:
                m_cfg.github_repo = repo_text
        if hasattr(self, "input_gh_token"):
            gh_tok = self.input_gh_token.text().strip()
            if gh_tok or not m_cfg.github_token:
                m_cfg.github_token = gh_tok
        if hasattr(self, "chk_gemini_enabled"):
            m_cfg.gemini_enabled = self.chk_gemini_enabled.isChecked()
        if hasattr(self, "combo_gemini_model"):
            m_cfg.gemini_model = self.combo_gemini_model.currentText().strip() or "gemini-3.8-flash"
        if hasattr(self, "input_gemini_key"):
            key_val = self.input_gemini_key.text().strip()
            if key_val:
                m_cfg.gemini_api_key = key_val
            elif getattr(self, "_user_edited_gemini_key", False):
                m_cfg.gemini_api_key = ""
        if hasattr(self, "slider_investment_stance"):
            idx = self.slider_investment_stance.value()
            if 0 <= idx < len(STANCE_KEYS):
                m_cfg.ai_investment_stance = STANCE_KEYS[idx]
        self.config.morning_report = m_cfg

    def _toggle_gemini_key_echo(self):
        if self.input_gemini_key.echoMode() == QLineEdit.Password:
            self.input_gemini_key.setEchoMode(QLineEdit.Normal)
            self.btn_toggle_gemini_key.setText("🙈")
        else:
            self.input_gemini_key.setEchoMode(QLineEdit.Password)
            self.btn_toggle_gemini_key.setText("👁️")

    def _test_gemini_connection(self):
        self._sync_morning_report_from_ui()
        api_key = self.input_gemini_key.text().strip()
        model = self.combo_gemini_model.currentText().strip() or "gemini-3.8-flash"

        if not api_key:
            QMessageBox.warning(self, "안내", "Gemini API 키를 먼저 입력해주세요.\n(Google AI Studio에서 무료로 즉시 발급받으실 수 있습니다)")
            return

        self.lbl_gemini_test_result.setText("⏳ Gemini API 호출 중...")
        self.lbl_gemini_test_result.setStyleSheet("color: #fbbf24;")
        self.btn_test_gemini.setEnabled(False)

        try:
            gemini = GeminiService(config=self.config, api_key=api_key, model=model)
            ok, msg = gemini.test_connection(model=model, api_key=api_key)
            if ok:
                # 연결 성공 시 즉시 config.yaml 및 .env에 영구 저장 (재실행 시 키 유지)
                try:
                    save_config(self.config)
                    self._persist_to_env("GEMINI_API_KEY", api_key)
                    self.settings_saved.emit()
                    save_note = "\n\n💡 API 키와 모델 설정이 안전하게 저장되어 재실행 시에도 유지됩니다."
                except Exception as save_err:
                    logger.warning(f"Gemini 설정 자동 저장 실패: {save_err}")
                    save_note = ""

                self.lbl_gemini_test_result.setText(f"✅ 연결 및 저장 완료 ({model})")
                self.lbl_gemini_test_result.setStyleSheet("color: #34d399; font-weight: bold;")
                QMessageBox.information(self, "Gemini AI 연결 및 저장 성공", msg + save_note)
            else:
                self.lbl_gemini_test_result.setText("❌ 연결 실패")
                self.lbl_gemini_test_result.setStyleSheet("color: #f87171; font-weight: bold;")
                QMessageBox.critical(self, "Gemini AI 연결 실패", f"오류 원인:\n{msg}")
        except Exception as e:
            self.lbl_gemini_test_result.setText("❌ 예외 발생")
            self.lbl_gemini_test_result.setStyleSheet("color: #f87171;")
            QMessageBox.critical(self, "오류", f"테스트 중 예외가 발생했습니다:\n{e}")
        finally:
            self.btn_test_gemini.setEnabled(True)

    def _save_gemini_settings_manually(self):
        """Gemini AI 설정 카드 전용 저장 버튼 핸들러"""
        self._sync_morning_report_from_ui()
        try:
            save_config(self.config)
            key = self.input_gemini_key.text().strip()
            if key:
                self._persist_to_env("GEMINI_API_KEY", key)
            self.settings_saved.emit()
            self.lbl_gemini_test_result.setText("💾 Gemini 설정이 저장되었습니다.")
            self.lbl_gemini_test_result.setStyleSheet("color: #38bdf8; font-weight: bold;")
            QMessageBox.information(
                self,
                "Gemini 설정 저장 완료",
                "Gemini API 설정이 안전하게 저장되었습니다.\n프로그램을 재실행해도 API 키와 모델이 기억됩니다.",
            )
        except Exception as e:
            logger.error(f"Gemini 설정 저장 실패: {e}")
            QMessageBox.critical(self, "저장 실패", f"Gemini 설정 저장 중 오류가 발생했습니다:\n{e}")

    def _auto_save_morning_report_settings(self):
        """입력 필드 수정(포커스 이동) 또는 모델/옵션 변경 시 config.yaml에 자동 반영 (키 유지 보장)"""
        if getattr(self, "_is_loading", False):
            return
        try:
            self._sync_morning_report_from_ui()
            save_config(self.config)
        except Exception as e:
            logger.debug(f"설정 백그라운드 자동 저장 예외(무시 가능): {e}")

    def _on_stance_slider_changed(self, value: int):
        """슬라이더 위치 변경 시 즉시 설명 카드를 갱신하고 설정을 자동 저장합니다."""
        self._update_stance_display(value)
        self._auto_save_morning_report_settings()

    def _update_stance_display(self, value: int):
        """선택된 단계(0~4)에 맞춰 성향 배지, 라벨, 색상 및 상세 조언 설명을 UI에 반영합니다."""
        if not (0 <= value < len(STANCE_KEYS)):
            value = 2
        key = STANCE_KEYS[value]
        profile = INVESTMENT_STANCE_PROFILES.get(key, INVESTMENT_STANCE_PROFILES["balanced"])
        label = profile.get("label", "")
        badge = profile.get("badge", "")
        desc = profile.get("description", "")

        colors = ["#38bdf8", "#67e8f9", "#c084fc", "#fb923c", "#f43f5e"]
        color = colors[value] if value < len(colors) else "#c084fc"

        if hasattr(self, "lbl_stance_title"):
            self.lbl_stance_title.setText(f"{badge} ({label})")
            self.lbl_stance_title.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {color};")
        if hasattr(self, "lbl_stance_desc"):
            self.lbl_stance_desc.setText(desc)

    def _open_kakao_guide(self):
        dlg = KakaoGuideDialog(self)
        dlg.exec()

    def _open_github_guide(self):
        dlg = GitHubGuideDialog(self)
        dlg.exec()

    def _check_cloud_status(self):
        self._sync_morning_report_from_ui()
        gh = GitHubService(self.config)
        ok, msg, data = gh.get_workflow_status()
        if ok:
            is_active = self.config.morning_report.github_cloud_enabled
            if is_active:
                self.lbl_cloud_status.setText("🟢 클라우드 활성화됨 (07:00 발송 대기)")
                self.lbl_cloud_status.setStyleSheet("font-weight: bold; color: #34d399; padding: 4px 8px; background: rgba(16,185,129,0.15); border-radius: 4px;")
            else:
                self.lbl_cloud_status.setText("⚪ 클라우드 비활성화됨 (중지 상태)")
                self.lbl_cloud_status.setStyleSheet("font-weight: bold; color: #94a3b8; padding: 4px 8px; background: rgba(255,255,255,0.05); border-radius: 4px;")
            QMessageBox.information(self, "클라우드 상태 조회", f"GitHub 워크플로우 상태:\n\n{msg}")
        else:
            QMessageBox.warning(self, "상태 조회 실패", f"GitHub 연동 오류:\n\n{msg}")

    def _enable_cloud(self):
        self._sync_morning_report_from_ui()
        gh = GitHubService(self.config)
        ok, msg = gh.enable_workflow()
        if ok:
            self.lbl_cloud_status.setText("🟢 클라우드 활성화됨 (07:00 발송 대기)")
            self.lbl_cloud_status.setStyleSheet("font-weight: bold; color: #34d399; padding: 4px 8px; background: rgba(16,185,129,0.15); border-radius: 4px;")
            QMessageBox.information(self, "클라우드 켜기 완료", f"{msg}")
        else:
            QMessageBox.critical(self, "클라우드 켜기 실패", f"{msg}")

    def _disable_cloud(self):
        self._sync_morning_report_from_ui()
        gh = GitHubService(self.config)
        ok, msg = gh.disable_workflow()
        if ok:
            self.lbl_cloud_status.setText("⚪ 클라우드 비활성화됨 (중지 상태)")
            self.lbl_cloud_status.setStyleSheet("font-weight: bold; color: #94a3b8; padding: 4px 8px; background: rgba(255,255,255,0.05); border-radius: 4px;")
            QMessageBox.information(self, "클라우드 끄기 완료", f"{msg}")
        else:
            QMessageBox.critical(self, "클라우드 끄기 실패", f"{msg}")

    def _trigger_cloud_now(self):
        self._sync_morning_report_from_ui()
        reply = QMessageBox.question(
            self,
            "클라우드 즉시 실행",
            "GitHub 클라우드 서버에 즉시 실행 신호를 보내시겠습니까?\n\n(PC가 꺼져 있어도 GitHub 러너가 돌아 카톡을 발송합니다)",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            gh = GitHubService(self.config)
            ok, msg = gh.trigger_workflow_dispatch()
            if ok:
                QMessageBox.information(self, "신호 전송 완료", f"{msg}")
            else:
                QMessageBox.critical(self, "신호 전송 실패", f"{msg}")

    def _preview_morning_report(self):
        self._sync_morning_report_from_ui()
        service = DailyReportService(self.config, self.repo)
        ok, msg, file_path = service.generate_and_send(send_kakao=False)
        if ok and file_path and file_path.exists():
            webbrowser.open(file_path.as_uri())
            QMessageBox.information(
                self,
                "웹 리포트 미리보기",
                f"모바일 웹 리포트가 성공적으로 생성되어 기본 웹 브라우저에서 열렸습니다:\n\n{file_path.name}",
            )
        else:
            QMessageBox.warning(self, "미리보기 실패", f"리포트 생성 실패:\n{msg}")

    def _test_kakao_send(self):
        self._sync_morning_report_from_ui()
        if not self.config.morning_report.kakao_access_token.strip():
            QMessageBox.warning(
                self,
                "토큰 누락",
                "카카오 Access Token이 입력되지 않았습니다.\n우측 상단의 [🔑 카카오톡 연동 가이드]를 확인하여 토큰을 입력해 주세요.",
            )
            return

        service = DailyReportService(self.config, self.repo)
        ok, msg, file_path = service.generate_and_send(send_kakao=True, force_kakao=True)
        if ok and "카카오톡 발송 성공" in msg:
            QMessageBox.information(self, "카카오톡 발송 완료", f"카카오톡으로 성공적으로 발송되었습니다!\n\n{msg}")
        elif ok:
            QMessageBox.warning(self, "카카오톡 미발송", f"리포트는 생성되었으나 카카오톡은 발송되지 않았습니다:\n\n{msg}")
        else:
            QMessageBox.critical(self, "발송 실패", f"카카오톡 발송 실패:\n\n{msg}")

    def _backup_db(self):
        try:
            backup_file = self.repo.backup_database()
            QMessageBox.information(
                self,
                "백업 완료",
                f"데이터베이스가 성공적으로 백업되었습니다:\n{backup_file}",
            )
        except Exception as e:
            QMessageBox.critical(self, "오류", f"DB 백업 실패: {e}")

    def _restore_db(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "복원할 백업 DB 파일 선택", "", "SQLite Database (*.db)"
        )
        if not file_path:
            return

        reply = QMessageBox.warning(
            self,
            "데이터베이스 복원 확인",
            "선택한 백업 파일로 현재 데이터베이스를 덮어씁니다.\n계속 진행하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            try:
                self.repo.restore_database(Path(file_path))
                QMessageBox.information(self, "복원 완료", "데이터베이스가 성공적으로 복원되었습니다.")
                self.settings_saved.emit()
            except Exception as e:
                QMessageBox.critical(self, "오류", f"DB 복원 실패: {e}")
