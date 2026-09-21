"""
ui/styles.py
PySide6 애플리케이션의 모던 다크 테마 스타일시트(QSS) 및 색상 토큰.
"""

APP_STYLESHEET = """
/* 전역 기본 설정 */
QWidget {
    background-color: #0f141c;
    color: #f1f5f9;
    font-family: 'Pretendard', 'Malgun Gothic', 'Segoe UI', sans-serif;
    font-size: 13px;
    selection-background-color: #3b82f6;
    selection-color: #ffffff;
}

/* 스크롤 영역 및 스크롤바 커스텀 */
QScrollArea {
    background-color: transparent;
    border: none;
}
QScrollArea > QWidget > QWidget {
    background-color: transparent;
}

QScrollBar:vertical {
    border: none;
    background: #0d131f;
    width: 10px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #374151;
    min-height: 25px;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover {
    background: #4b5563;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}


QScrollBar:horizontal {
    border: none;
    background: #111827;
    height: 8px;
    margin: 0px;
}
QScrollBar::handle:horizontal {
    background: #374151;
    min-width: 20px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal:hover {
    background: #4b5563;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* 좌측 사이드바 */
#Sidebar {
    background-color: #141b26;
    border-right: 1px solid #1f2937;
}
#AppTitle {
    font-size: 16px;
    font-weight: bold;
    color: #38bdf8;
    padding: 18px 12px 12px 12px;
}
#AppSubtitle {
    font-size: 11px;
    color: #94a3b8;
    padding: 0px 12px 16px 12px;
}

/* 사이드바 네비게이션 버튼 */
QPushButton.nav-btn {
    text-align: left;
    padding: 12px 16px;
    border: none;
    border-radius: 8px;
    margin: 3px 8px;
    color: #94a3b8;
    font-size: 13px;
    font-weight: 500;
    background-color: transparent;
}
QPushButton.nav-btn:hover {
    background-color: #1e293b;
    color: #f8fafc;
}
QPushButton.nav-btn:checked {
    background-color: #1d4ed8;
    color: #ffffff;
    font-weight: bold;
}

/* 메인 헤더 */
#HeaderPanel {
    background-color: #141b26;
    border-bottom: 1px solid #1f2937;
    padding: 10px 24px;
}
#PageTitle {
    font-size: 20px;
    font-weight: bold;
    color: #f8fafc;
}

/* 계좌 선택 드롭다운 (헤더용) */
QComboBox#AccountSelectorComboBox {
    background-color: #1e293b;
    color: #38bdf8;
    border: 1px solid #3b82f6;
    border-radius: 6px;
    padding: 4px 12px 4px 10px;
    font-weight: 600;
    font-size: 13px;
    min-width: 180px;
    height: 32px;
}
QComboBox#AccountSelectorComboBox:hover {
    background-color: #273549;
    border-color: #60a5fa;
}
QComboBox#AccountSelectorComboBox::drop-down {
    border: none;
    width: 20px;
}
QComboBox#AccountSelectorComboBox QAbstractItemView {
    background-color: #1e293b;
    color: #f1f5f9;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 4px;
}

/* 투자 주기 및 D-day 배지 */
QLabel#CycleBadge {
    background-color: #13273e;
    color: #38bdf8;
    border: 1px solid #0284c7;
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 12px;
    font-weight: 600;
}

/* 카드 패널 */
QFrame.card {
    background-color: #182232;
    border: 1px solid #233044;
    border-radius: 12px;
    padding: 16px;
}
QFrame.card:hover {
    border-color: #334155;
}

/* 메트릭 카드 텍스트 */
QLabel.card-title {
    color: #94a3b8;
    font-size: 12px;
    font-weight: 500;
}
QLabel.card-value {
    color: #f8fafc;
    font-size: 22px;
    font-weight: bold;
}
QLabel.card-badge {
    font-size: 11px;
    font-weight: 600;
    padding: 2px 6px;
    border-radius: 4px;
}

/* 기본 버튼 */
QPushButton.primary-btn {
    background-color: #2563eb;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 600;
}
QPushButton.primary-btn:hover {
    background-color: #1d4ed8;
}
QPushButton.primary-btn:pressed {
    background-color: #1e40af;
}

QPushButton.secondary-btn {
    background-color: #243042;
    color: #e2e8f0;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 500;
}
QPushButton.secondary-btn:hover {
    background-color: #334155;
}

QPushButton.danger-btn {
    background-color: #dc2626;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 6px 12px;
    font-weight: 600;
}
QPushButton.danger-btn:hover {
    background-color: #b91c1c;
}

/* 테이블 스타일 */
QTableWidget {
    background-color: #141c28;
    border: 1px solid #1f2937;
    border-radius: 8px;
    gridline-color: #1e293b;
    font-size: 12px;
}
QHeaderView::section {
    background-color: #182232;
    color: #94a3b8;
    padding: 6px 6px;
    border: none;
    border-bottom: 1px solid #283548;
    border-right: 1px solid #1f2937;
    font-weight: 600;
    font-size: 12px;
}
QHeaderView::section:hover {
    background-color: #1e293b;
    color: #f8fafc;
}
QTableWidget::item {
    padding: 4px 6px;
    border-bottom: 1px solid #1a2332;
}
QTableWidget::item:selected {
    background-color: #1e3a8a;
    color: #ffffff;
}

/* 입력 필드 (상하 텍스트 잘림 방지 및 여유로운 높이 확보) */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: #141c28;
    border: 1px solid #334155;
    border-radius: 6px;
    color: #f8fafc;
    font-size: 13px;
    min-height: 36px;
    padding: 2px 10px;
}

QLineEdit {
    padding: 4px 10px;
}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #3b82f6;
    background-color: #162235;
}

/* 콤보박스 스타일 및 드롭다운 버튼 */
QComboBox {
    padding-right: 32px;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 28px;
    border-left: 1px solid #334155;
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
    background-color: #1a2333;
}

QComboBox::drop-down:hover {
    background-color: #243044;
}

QComboBox::down-arrow {
    subcontrol-origin: content;
    subcontrol-position: center;
    width: 0px;
    height: 0px;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 5px solid #94a3b8;
}

QComboBox QAbstractItemView {
    background-color: #141c28;
    border: 1px solid #3b82f6;
    border-radius: 6px;
    color: #f8fafc;
    selection-background-color: #1e3a8a;
    selection-color: #ffffff;
    padding: 4px;
    outline: none;
}

QComboBox QAbstractItemView::item {
    min-height: 32px;
    padding: 4px 10px;
}

/* 스핀박스 상하 증감 버튼 스타일 */
QSpinBox, QDoubleSpinBox {
    padding-right: 28px;
}

QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 24px;
    height: 18px;
    border-left: 1px solid #334155;
    border-bottom: 1px solid #334155;
    border-top-right-radius: 5px;
    background-color: #1a2333;
}

QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover {
    background-color: #243044;
}

QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    subcontrol-origin: content;
    subcontrol-position: center;
    width: 0px;
    height: 0px;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 4px solid #94a3b8;
}

QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 24px;
    height: 18px;
    border-left: 1px solid #334155;
    border-bottom-right-radius: 5px;
    background-color: #1a2333;
}

QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: #243044;
}

QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    subcontrol-origin: content;
    subcontrol-position: center;
    width: 0px;
    height: 0px;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 4px solid #94a3b8;
}

/* 전역 툴팁 스타일 (다크 배경 및 네온 테두리) */
QToolTip {
    background-color: #0b1120;
    color: #f8fafc;
    border: 1px solid #38bdf8;
    border-radius: 6px;
    padding: 6px 10px;
    font-family: 'Malgun Gothic', 'Pretendard', sans-serif;
    font-size: 9.5pt;
}
"""
