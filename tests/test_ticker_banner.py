"""
tests/test_ticker_banner.py
상단 전광판 (TickerBanner) 위젯 단위 테스트.
- comment.txt 로드 및 코멘트 파싱 검증
- 3초 타이머 및 롤링 로직 검증
- 이전/다음 수동 조작 및 일시정지 기능 검증
"""

import pytest
from PySide6.QtCore import Qt
from ui.widgets.ticker_banner import TickerBanner
from core.paths import get_project_root


def test_ticker_banner_load_comments(qtbot, tmp_path):
    """comment.txt 로드 및 3초 타이머 설정 검증"""
    dummy_file = tmp_path / "comment.txt"
    dummy_file.write_text("첫 번째 원칙\n두 번째 원칙\n세 번째 원칙", encoding="utf-8")

    banner = TickerBanner(comment_file=dummy_file)
    qtbot.addWidget(banner)

    assert len(banner.comments) == 3
    assert banner.timer.interval() == 3000
    assert banner.current_index == 0
    assert "첫 번째 원칙" in banner.text_label.text()
    assert banner.count_label.text() == "1/3"


def test_ticker_banner_navigation_and_pause(qtbot, tmp_path):
    """다음/이전 및 일시정지 동작 검증"""
    dummy_file = tmp_path / "comment.txt"
    dummy_file.write_text("원칙 1\n원칙 2\n원칙 3", encoding="utf-8")

    banner = TickerBanner(comment_file=dummy_file)
    qtbot.addWidget(banner)

    # 1. 다음 코멘트
    banner.next_comment()
    assert banner.current_index == 1
    assert banner.count_label.text() == "2/3"

    # 2. 다음 코멘트
    banner.next_comment()
    assert banner.current_index == 2
    assert banner.count_label.text() == "3/3"

    # 3. 롤링 순환 (마지막 -> 처음)
    banner.next_comment()
    assert banner.current_index == 0
    assert banner.count_label.text() == "1/3"

    # 4. 이전 코멘트 (처음 -> 마지막)
    banner.prev_comment()
    assert banner.current_index == 2
    assert banner.count_label.text() == "3/3"

    # 5. 일시정지 토글
    banner.toggle_pause()
    assert banner.is_paused is True
    assert not banner.timer.isActive()

    banner.toggle_pause()
    assert banner.is_paused is False
    assert banner.timer.isActive()


def test_ticker_banner_real_comment_file(qtbot):
    """실제 프로젝트 루트의 comment.txt 로드 검증"""
    banner = TickerBanner()
    qtbot.addWidget(banner)

    # comment.txt에 최소 40개 이상의 코멘트가 정상 탑재되어 있어야 함
    assert len(banner.comments) >= 40
    assert banner.timer.interval() == 3000
    assert banner.timer.isActive()
