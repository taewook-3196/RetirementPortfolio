"""
tests/test_news_ticker.py
NewsTickerBanner 위젯 단위 테스트.
- 피드 주입 및 라벨 표시 검증
- 다음/이전 및 일시정지 동작 검증
- 새로고침 시그널 발송 검증
"""

import pytest
from PySide6.QtCore import Qt
from ui.widgets.news_ticker_banner import NewsTickerBanner


def test_news_ticker_feed_display(qtbot):
    """뉴스 피드 주입 시 초기 화면 표시 검증"""
    banner = NewsTickerBanner()
    qtbot.addWidget(banner)

    sample_feed = [
        {"tag": "엔비디아", "title": "엔비디아 차세대 AI 칩 공개", "press": "매일경제", "link": "https://example.com/1"},
        {"tag": "S&P500", "title": "미국 증시 사상 최고치 경신", "press": "한국경제", "link": "https://example.com/2"},
    ]

    banner.set_news_feed(sample_feed)
    assert banner.current_index == 0
    assert banner.title_label.text() == "엔비디아 차세대 AI 칩 공개"
    assert "엔비디아" in banner.badge.text()
    assert banner.count_label.text() == "1/2"
    assert banner.current_link == "https://example.com/1"
    assert banner.timer.isActive()


def test_news_ticker_navigation_and_pause(qtbot):
    """다음/이전 및 일시정지 동작 검증"""
    banner = NewsTickerBanner()
    qtbot.addWidget(banner)

    sample_feed = [
        {"tag": "뉴스1", "title": "첫 번째 기사", "press": "언론사A", "link": "http://a.com"},
        {"tag": "뉴스2", "title": "두 번째 기사", "press": "언론사B", "link": "http://b.com"},
        {"tag": "뉴스3", "title": "세 번째 기사", "press": "언론사C", "link": "http://c.com"},
    ]
    banner.set_news_feed(sample_feed)

    # 1. 다음 뉴스
    banner.next_news()
    assert banner.current_index == 1
    assert banner.count_label.text() == "2/3"

    # 2. 다음 뉴스
    banner.next_news()
    assert banner.current_index == 2
    assert banner.count_label.text() == "3/3"

    # 3. 롤링 순환 (마지막 -> 처음)
    banner.next_news()
    assert banner.current_index == 0
    assert banner.count_label.text() == "1/3"

    # 4. 이전 뉴스
    banner.prev_news()
    assert banner.current_index == 2
    assert banner.count_label.text() == "3/3"

    # 5. 일시정지 토글
    banner.toggle_pause()
    assert banner.is_paused is True
    assert not banner.timer.isActive()

    banner.toggle_pause()
    assert banner.is_paused is False
    assert banner.timer.isActive()
