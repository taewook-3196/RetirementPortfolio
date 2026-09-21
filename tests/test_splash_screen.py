"""
tests/test_splash_screen.py
GoldenPigSplashScreen 단위 테스트.
- 스플래시 화면 초기화 및 3D 황금복돼지 에셋 로드 확인
- 애니메이션 타이머 및 시그널 방출 검증
- 클릭/키 입력 시 즉시 스킵(Instant Skip) 동작 검증
"""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from ui.widgets.splash_screen import GoldenPigSplashScreen
from core.paths import get_golden_pig_path


def test_splash_screen_init(qtbot):
    """스플래시 화면 초기화 및 에셋 로드 확인"""
    splash = GoldenPigSplashScreen(duration_ms=500)
    qtbot.addWidget(splash)

    assert splash.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert splash.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert splash.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert splash.width() == 480
    assert splash.height() == 560
    assert "부자 되세요" in splash.title_label.text()
    assert splash.progress_bar.value() == 15


def test_splash_screen_finish_signal(qtbot):
    """타이머 완료 시 finished 시그널 방출 및 창 종료 검증"""
    splash = GoldenPigSplashScreen(duration_ms=100)
    qtbot.addWidget(splash)

    with qtbot.waitSignal(splash.finished, timeout=1500):
        splash.start_animation()


def test_splash_screen_instant_skip_on_click(qtbot):
    """마우스 클릭 시 즉시 페이드아웃 및 finished 시그널 방출 검증"""
    splash = GoldenPigSplashScreen(duration_ms=5000)
    qtbot.addWidget(splash)

    splash.start_animation()
    with qtbot.waitSignal(splash.finished, timeout=1000):
        qtbot.mouseClick(splash, Qt.MouseButton.LeftButton)


def test_splash_screen_option_in_settings(qtbot, tmp_path):
    """환경 설정 화면에서 황금돼지 인트로 켜기/끄기 옵션 제어 검증"""
    from core.config import get_default_config, save_config, load_config
    from database.connection import init_db
    from database.repository import Repository
    from ui.settings_page import SettingsPage

    db_path = tmp_path / "test_splash_cfg.db"
    init_db(db_path)
    repo = Repository(db_path)

    cfg_file = tmp_path / "config.yaml"
    cfg = get_default_config()
    cfg.show_splash_screen = True
    save_config(cfg, cfg_file)

    page = SettingsPage(config=cfg, repo=repo)
    qtbot.addWidget(page)

    # 1. 초기 상태: 표시 (True) 선택 상태
    assert hasattr(page, "combo_splash")
    assert page.combo_splash.count() == 2
    assert page.combo_splash.currentData() is True

    # 2. '끄기'로 변경 후 설정 저장 동작 시뮬레이션
    page.combo_splash.setCurrentIndex(1)
    assert page.combo_splash.currentData() is False

    # _save_settings 호출 시 config에 반영 확인
    page.config.show_splash_screen = bool(page.combo_splash.currentData())
    save_config(page.config, cfg_file)

    reloaded = load_config(cfg_file)
    assert reloaded.show_splash_screen is False

    # 3. refresh() 호출 시 콤보박스 동기화 확인
    page.config = reloaded
    page.refresh()
    assert page.combo_splash.currentIndex() == 1
    assert page.combo_splash.currentData() is False

