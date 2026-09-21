"""
tests/test_phase5_ui.py
Phase 5~9 GUI 검증 테스트 (pytest-qt 활용):
- MainWindow 초기화 및 6대 페이지 생성
- 사이드바 네비게이션 페이지 전환 동작
- 대시보드, 포트폴리오, 매수추천, 거래내역, 시장데이터, 설정 화면 렌더링
"""

import pytest
from PySide6.QtWidgets import QApplication
from core.config import get_default_config
from database.connection import init_db
from database.repository import Repository
from ui.main_window import MainWindow


@pytest.fixture
def app_window(qtbot, tmp_path, monkeypatch):
    """테스트용 임시 DB 기반 MainWindow 픽스처"""
    db_file = tmp_path / "gui_test.db"
    init_db(db_file)
    repo = Repository(db_file)
    cfg = get_default_config()
    cfg.data_source = "mock"

    # UI 테스트 중에는 백그라운드 네트워크 쓰레드 충돌 방지를 위해 목 피드 주입
    monkeypatch.setattr(
        "services.news_service.NewsService.get_news_feed",
        lambda *args, **kwargs: [
            {"tag": "테스트", "title": "테스트 뉴스 제목", "press": "테스트언론", "datetime": "", "link": "https://example.com", "category": "test"}
        ]
    )

    window = MainWindow(repo=repo, config=cfg)
    qtbot.addWidget(window)
    yield window, repo
    window.close()


def test_main_window_initialization(app_window):
    """메인 윈도우 초기 상태 및 6개 페이지 탑재 확인"""
    window, repo = app_window
    assert window.windowTitle() == "개인 퇴직연금 ETF 포트폴리오 관리 시스템"
    assert window.stack.count() == 6
    assert window.stack.currentIndex() == 0
    assert window.page_title.text() == "대시보드"


def test_sidebar_navigation_switch(app_window):
    """사이드바 버튼 클릭을 통한 페이지 전환 검증"""
    window, _ = app_window

    # 1: 포트폴리오
    window._switch_page(1)
    assert window.stack.currentIndex() == 1
    assert window.page_title.text() == "포트폴리오 상세"

    # 2: 매수추천
    window._switch_page(2)
    assert window.stack.currentIndex() == 2
    assert window.page_title.text() == "월간 매수 추천"

    # 3: 거래내역
    window._switch_page(3)
    assert window.stack.currentIndex() == 3
    assert window.page_title.text() == "거래내역 관리"

    # 4: 시장데이터
    window._switch_page(4)
    assert window.stack.currentIndex() == 4
    assert window.page_title.text() == "시장 데이터 분석"

    # 5: 환경설정
    window._switch_page(5)
    assert window.stack.currentIndex() == 5
    assert window.page_title.text() == "환경 설정"


def test_dashboard_and_recommendation_render(app_window):
    """대시보드 KPI 카드 및 추천 테이블 렌더링 검증"""
    window, repo = app_window

    # 모의 거래 추가
    repo.add_transaction("2026-09-01", "442560", "BUY", quantity=100, price=16000)
    window._refresh_current_page()

    assert window.page_dashboard.card_invested.value_label.text() != ""
    assert window.page_dashboard.table.rowCount() == 3

    # 추천 페이지 모드 전환 검증
    rec_page = window.page_rec
    rec_page.refresh()
    assert rec_page._current_mode == "monthly"
    assert rec_page.table.columnCount() == 15

    rec_page.btn_mode_rebalance.click()
    assert rec_page._current_mode == "rebalance"
    assert rec_page.table.columnCount() == 11
    assert "자산 기준 리밸런싱" in rec_page.info_lbl.text()

    rec_page.btn_mode_monthly.click()
    assert rec_page._current_mode == "monthly"
    assert rec_page.table.columnCount() == 15


def test_market_data_watchlist_and_chart_tooltip(app_window):
    """시장 데이터 화면 관심 종목 표시 및 차트 툴팁 동작 검증"""
    window, repo = app_window

    # 관심 종목 추가
    from core.config import WatchlistConfig
    window.config.watchlist.append(WatchlistConfig(ticker="069500", name="KODEX 200"))
    window.page_market.update_etf_list(window.config)

    # 콤보박스에 [포트폴리오] 및 [관심종목] 포함 확인
    items = [window.page_market.combo_ticker.itemText(i) for i in range(window.page_market.combo_ticker.count())]
    assert any("[포트폴리오]" in item for item in items)
    assert any("[관심종목]" in item and "069500" in item for item in items)

    # 차트 plot 및 툴팁 메서드 동작 검증
    dates = ["20260910", "20260911"]
    prices = [10000.0, 10200.0]
    details = [
        {"date": "20260910", "open": 9900, "high": 10100, "low": 9800, "close": 10000, "volume": 50000, "nav": 10005.0},
        {"date": "20260911", "open": 10050, "high": 10300, "low": 10000, "close": 10200, "volume": 60000, "nav": 10202.0},
    ]
    chart = window.page_market.chart
    chart.plot(dates, prices, "KODEX 200", high_price=10500, details=details)
    assert chart._valid_dates == dates
    assert chart._valid_prices == prices
    assert len(chart._details) == 2
    assert chart._cursor_line is not None

    # 마우스 이동 및 이탈 시뮬레이션
    class MockEvent:
        inaxes = chart._ax
        xdata = 1.0

    chart._on_mouse_move(MockEvent())
    assert chart._cursor_line.get_visible() is True
    assert chart._highlight_dot.get_visible() is True

    chart._on_figure_leave(None)
    assert chart._cursor_line.get_visible() is False


def test_etf_search_dialog_interaction(app_window):
    """ETF 종목 검색 다이얼로그 검색 및 선택 상호작용 검증"""
    window, repo = app_window
    from ui.widgets.etf_search_dialog import ETFSearchDialog

    dlg = ETFSearchDialog(repo, window)
    dlg.search_input.setText("TDF")
    assert dlg.table.rowCount() > 0

    # 첫 번째 행 선택 확인
    dlg._on_select()
    assert dlg.selected_item is not None
    assert "TDF" in dlg.selected_item[1]


def test_watchlist_dialog_interactions(app_window):
    """관심종목 다이얼로그 테이블 조작(행 추가, 삭제) 및 속성 검증"""
    window, repo = app_window
    from ui.market_data_page import WatchlistDialog

    dlg = WatchlistDialog(window.config, repo=repo, parent=window)
    assert hasattr(dlg, "table")
    assert dlg.table is not None
    init_rows = dlg.table.rowCount()

    # 행 추가
    dlg._add_row()
    assert dlg.table.rowCount() == init_rows + 1

    # 마지막 행 선택 후 삭제
    dlg.table.setCurrentCell(init_rows, 0)
    dlg._del_row()
    assert dlg.table.rowCount() == init_rows


def test_transaction_dialog_ticker_name_sync(app_window):
    """거래 추가 다이얼로그 종목코드 및 종목명 양방향 연동 검증"""
    window, repo = app_window
    from ui.transactions_page import TransactionDialog

    tickers = [
        ("442560", "TIGER 차이나전기차SOLACTIVE"),
        ("379800", "KODEX 미국나스닥100TR"),
        ("360750", "TIGER 미국S&P500"),
    ]

    dlg = TransactionDialog(tickers, repo=repo, parent=window)
    assert hasattr(dlg, "combo_ticker")
    assert hasattr(dlg, "combo_name")
    assert dlg.combo_ticker.count() >= 3
    assert dlg.combo_name.count() == dlg.combo_ticker.count()

    # 1. 종목코드 1번 인덱스(379800) 선택 시 종목명 연동 확인
    dlg.combo_ticker.setCurrentIndex(1)
    assert dlg.combo_ticker.currentText() == "379800"
    assert dlg.combo_name.currentText() == "KODEX 미국나스닥100TR"
    assert dlg.combo_name.currentIndex() == 1

    # 2. 종목명 2번 인덱스(TIGER 미국S&P500) 선택 시 종목코드 연동 확인
    dlg.combo_name.setCurrentIndex(2)
    assert dlg.combo_ticker.currentText() == "360750"
    assert dlg.combo_name.currentText() == "TIGER 미국S&P500"
    assert dlg.combo_ticker.currentIndex() == 2

    # 3. get_data() 추출 데이터 검증
    data = dlg.get_data()
    assert data["ticker"] == "360750"
    assert data["quantity"] == 10
    assert data["type"] == "BUY"

    # 4. 수정 모드(tx_data 지정) 시 자동 선택 검증
    edit_dlg = TransactionDialog(tickers, tx_data={"ticker": "379800", "type": "SELL", "quantity": 50, "price": 18000}, repo=repo, parent=window)
    assert edit_dlg.combo_ticker.currentText() == "379800"
    assert edit_dlg.combo_name.currentText() == "KODEX 미국나스닥100TR"
    edit_data = edit_dlg.get_data()
    assert edit_data["ticker"] == "379800"
    assert edit_data["quantity"] == 50
    assert edit_data["type"] == "SELL"


def test_multi_account_ui_interaction(app_window):
    """메인 윈도우 계좌 선택 콤보박스 및 다중 계좌 UI 상호작용 검증"""
    window, repo = app_window
    from ui.settings_page import AccountDialog

    # 1. 초기 콤보박스 상태 확인 (전체 통합 + 기본 계좌)
    assert window.combo_account.count() >= 2
    assert "🌐 전체 계좌 (통합)" in window.combo_account.itemText(0)

    # 2. 신규 계좌 생성 및 콤보 갱신
    acc2 = repo.create_account(
        account_name="KB ISA 계좌",
        account_number="202-1234",
        broker="KB증권",
        initial_capital=30000000.0,
        base_monthly=2000000.0,
        max_additional_monthly=1000000.0,
        buy_cycle_type="weekly",
        buy_cycle_detail="MON",
    )
    window._populate_account_selector(keep_selection=True)
    item_texts = [window.combo_account.itemText(i) for i in range(window.combo_account.count())]
    assert any("KB ISA 계좌" in t for t in item_texts)

    # 3. KB ISA 계좌 선택 시 대시보드 연동 확인
    for i in range(window.combo_account.count()):
        if window.combo_account.itemData(i) == acc2.id:
            window.combo_account.setCurrentIndex(i)
            break

    assert "KB ISA 계좌" in window.page_dashboard.plan_title.text()
    assert "매주 월요일" in window.page_dashboard.badge_cycle.text()

    # 4. 전체 통합 선택 시 대시보드 연동 확인
    window.combo_account.setCurrentIndex(0)
    assert window.page_dashboard.plan_title.text() == "전체 통합 투자 계획"
    assert "전체 계좌 통합" in window.page_dashboard.badge_cycle.text()

    # 5. AccountDialog 상호작용 검증
    dlg = AccountDialog(parent=window)
    dlg.input_name.setText("테스트 계좌")
    dlg.combo_cycle_type.setCurrentIndex(1)  # 매주 (특정 요일)
    dlg._on_cycle_type_changed()
    assert dlg.combo_cycle_detail.isEnabled() is True
    assert dlg.combo_cycle_detail.count() == 5  # 월~금

    dlg.combo_cycle_type.setCurrentIndex(6)  # 투자 주기 없음
    dlg._on_cycle_type_changed()
    assert dlg.combo_cycle_detail.isEnabled() is False
    dlg.close()


def test_settings_page_account_target_linking(app_window):
    """환경 설정 탭에서 계좌 선택 시 목표 비중 연동 및 100% 미만 현금 표시 검증"""
    window, repo = app_window
    settings = window.page_settings

    # 1. 명칭 및 기본 타이틀 확인
    assert settings.etf_title.text() == "목표 비중 설정"

    # 2. 계좌 관리 테이블에 계좌가 로드되어 있는지 확인
    assert settings.table_accounts.rowCount() >= 1
    default_acc = repo.get_default_account()
    assert default_acc.account_name in settings.lbl_selected_acc_name.text()

    # 3. 신규 계좌 추가 후 계좌 선택 전환
    acc2 = repo.create_account(
        account_name="연동 테스트 계좌",
        initial_capital=50000000.0,
    )
    from core.config import ETFConfig
    repo.save_account_targets(acc2.id, [
        ETFConfig(ticker="069500", name="KODEX 200", target_weight=0.70)
    ])
    settings._refresh_accounts_table()

    # acc2 행 선택
    target_row = -1
    for r in range(settings.table_accounts.rowCount()):
        if settings.table_accounts.item(r, 0).text() == str(acc2.id):
            target_row = r
            break
    assert target_row >= 0

    settings.table_accounts.selectRow(target_row)
    assert "연동 테스트 계좌" in settings.lbl_selected_acc_name.text()
    assert settings.table.rowCount() == 1
    assert settings.table.item(0, 0).text() == "069500"
    assert "70.0" in settings.table.item(0, 2).text()

    # 4. 100% 미만 시 현금 표기 확인 (목표 합계: 70.0% (현금: 30.0%))
    assert "70.0%" in settings.lbl_weight_sum.text()
    assert "현금: 30.0%" in settings.lbl_weight_sum.text()
    assert "#34d399" in settings.lbl_weight_sum.styleSheet()

    # 5. 100% 초과 시 경고 표기 확인
    settings.table.item(0, 2).setText("120.0")
    settings._on_table_cell_changed()
    assert "100% 초과" in settings.lbl_weight_sum.text()
    assert "#f87171" in settings.lbl_weight_sum.styleSheet()


def test_settings_page_investment_stance_slider(app_window):
    """설정 화면에서 AI 투자 조언 방향성(투자 성향) 슬라이더 조작 및 반영 검증"""
    window, repo = app_window
    settings = window.page_settings

    assert hasattr(settings, "slider_investment_stance")
    assert hasattr(settings, "lbl_stance_title")
    assert hasattr(settings, "lbl_stance_desc")

    # 1. 초기값 확인 (기본값: balanced, slider value 2)
    assert settings.slider_investment_stance.value() == 2
    assert "중립/균형" in settings.lbl_stance_title.text()

    # 2. 슬라이더를 0 (매우 보수적)으로 변경
    settings.slider_investment_stance.setValue(0)
    assert "매우 보수적" in settings.lbl_stance_title.text()
    assert "원금 보존" in settings.lbl_stance_desc.text()
    assert settings.config.morning_report.ai_investment_stance == "very_conservative"

    # 3. 슬라이더를 4 (매우 공격적)으로 변경
    settings.slider_investment_stance.setValue(4)
    assert "매우 공격적" in settings.lbl_stance_title.text()
    assert "수익 극대화" in settings.lbl_stance_desc.text()
    assert settings.config.morning_report.ai_investment_stance == "very_aggressive"

    # 4. 슬라이더를 3 (공격적)으로 변경
    settings.slider_investment_stance.setValue(3)
    assert "공격적" in settings.lbl_stance_title.text()
    assert settings.config.morning_report.ai_investment_stance == "aggressive"






