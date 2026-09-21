"""
main.py
개인 퇴직연금 ETF 포트폴리오 관리 데스크톱 애플리케이션 진입점.
Windows Portable 환경 지원:
- 별도의 DB/웹서버 설치 불필요
- 단일 폴더 이동/복사 실행 가능
- PySide6 기반 고성능 네이티브 GUI
"""

from __future__ import annotations
import sys
from PySide6.QtWidgets import QApplication
from core.paths import ensure_directories, get_database_path
from core.config import load_config
from core.logging_config import setup_logging
from database.connection import init_db
from database.repository import Repository
from ui.styles import APP_STYLESHEET
from ui.main_window import MainWindow

# Windows SSL 인증서 호환성 주입 (KRX Open API 접속용)
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass


def main():
    # 1. 필수 디렉터리 생성 및 전역 로거 설정
    ensure_directories()
    logger = setup_logging()
    logger.info("=" * 60)
    logger.info("퇴직연금 ETF 포트폴리오 관리 프로그램을 시작합니다.")

    # 2. 설정 파일 로드
    config = load_config()
    logger.info("설정 로드 완료: data_source=%s, 초기자본=%s원", config.data_source, f"{config.initial_capital:,}")

    # 3. SQLite 데이터베이스 및 테이블 자동 초기화
    db_path = get_database_path()
    init_db(db_path)
    logger.info("SQLite DB 연결 및 테이블 초기화 완료: %s", db_path)

    repo = Repository(db_path)

    # CLI 백그라운드 모닝 리포트 발송 모드 지원 (--daily-report)
    if "--daily-report" in sys.argv:
        from services.daily_report_service import DailyReportService
        logger.info("[CLI] 모닝 리포트 자동 생성 및 발송 모드로 시작합니다.")
        service = DailyReportService(config=config, repo=repo)
        ok, msg, file_path = service.generate_and_send(send_kakao=True)
        if ok:
            logger.info("[CLI] 모닝 리포트 발송 성공: %s (파일: %s)", msg, file_path)
            print(f"SUCCESS: {msg}")
            sys.exit(0)
        else:
            logger.error("[CLI] 모닝 리포트 발송 실패: %s", msg)
            print(f"FAILED: {msg}", file=sys.stderr)
            sys.exit(1)

    # Windows 작업표시줄 고유 아이콘 표출을 위한 AppUserModelID 설정
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("mycompany.retirementportfolio.pension.1.0")
    except Exception:
        pass

    # 4. PySide6 애플리케이션 생성 및 스타일시트/아이콘 적용
    from PySide6.QtCore import Qt
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    from PySide6.QtGui import QFont, QIcon
    from core.paths import get_icon_path

    icon_path = get_icon_path()
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    app.setFont(QFont("Malgun Gothic", 10))
    app.setStyleSheet(APP_STYLESHEET)

    # 5. 황금복돼지 스플래시 인트로 또는 즉시 실행
    show_splash = getattr(config, "show_splash_screen", True)
    if show_splash:
        from ui.widgets.splash_screen import GoldenPigSplashScreen
        from PySide6.QtCore import QTimer
        splash = GoldenPigSplashScreen(min_display_ms=2800)
        splash.start_animation()
        splash.set_progress(20, "진지하게 시장 데이터 및 포트폴리오 분석 중...")

        window: MainWindow | None = None

        def on_splash_finished():
            nonlocal window
            if window:
                window.show()
                window.activateWindow()
                window.raise_()
                logger.info("메인 GUI 창이 활성화되었습니다.")

        splash.finished.connect(on_splash_finished)

        def load_application():
            nonlocal window
            splash.set_progress(60, "씨익~ 대박 기운 감지! 매수 찬스 포착 중...")
            window = MainWindow(repo=repo, config=config)
            if icon_path.exists():
                window.setWindowIcon(QIcon(str(icon_path)))
            splash.set_progress(100, "복(福)이 넝쿨째! 부자 되세요~ 🐷✨")
            splash.mark_ready()

        # 이벤트 루프 시작 직후 스플래시가 첫 화면과 바운스 모션을 부드럽게 렌더링할 수 있도록 150ms 후 로딩 시작
        QTimer.singleShot(150, load_application)
    else:
        logger.info("황금돼지 스플래시 인트로가 비활성화되어 메인 화면을 즉시 실행합니다.")
        window = MainWindow(repo=repo, config=config)
        if icon_path.exists():
            window.setWindowIcon(QIcon(str(icon_path)))
        window.show()
        window.activateWindow()
        window.raise_()
        logger.info("메인 GUI 창이 활성화되었습니다.")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
