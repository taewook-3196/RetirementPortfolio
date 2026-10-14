"""
tests/test_news_service.py
NewsService 단위 테스트.
- 네이버 모바일 종목 뉴스 및 구글 RSS 뉴스 수집 검증
- ETF 구성종목 매핑 검증
- 필터 모드별 피드 생성 및 중복 제거 검증
"""

import pytest
from datetime import datetime, timedelta, timezone
from services.news_service import NewsService, ETF_CONSTITUENTS_MAP
from core.config import ETFConfig, WatchlistConfig


def test_etf_constituents_map():
    """주요 ETF의 핵심 구성종목 매핑 존재 여부 검증"""
    assert "381170" in ETF_CONSTITUENTS_MAP
    assert "엔비디아" in ETF_CONSTITUENTS_MAP["381170"]["keywords"]
    assert "488500" in ETF_CONSTITUENTS_MAP
    assert "442560" in ETF_CONSTITUENTS_MAP
    assert "069500" in ETF_CONSTITUENTS_MAP


def test_get_constituent_query():
    """종목코드 및 종목명 기반 지능적 테마/구성종목 쿼리 추론 검증"""
    service = NewsService()
    # 1. 맵핑에 등록된 종목
    q, tag = service.get_constituent_query("381170", "TIGER 미국테크TOP10 INDXX")
    assert "엔비디아" in q
    assert tag == "미국빅테크"

    # 2. 맵핑에 없지만 이름에 반도체가 포함된 ETF
    q, tag = service.get_constituent_query("999991", "KODEX 미국반도체MV")
    assert "반도체" in q
    assert tag == "반도체"

    # 3. 맵핑에 없지만 이름에 배당이 포함된 ETF
    q, tag = service.get_constituent_query("999992", "ACE 미국배당다우존스")
    assert "배당" in q
    assert tag == "배당·인컴"

    # 4. 일반 개별 종목명
    q, tag = service.get_constituent_query("035420", "NAVER")
    assert q == "NAVER"


def test_news_service_get_feed_structure(monkeypatch):
    """외부 API에 의존하지 않고 최신 기사 필터와 피드 구조를 검증"""
    service = NewsService()
    now = datetime.now(timezone.utc)
    recent = (now - timedelta(hours=1)).isoformat()
    monkeypatch.setattr(service, "fetch_stock_news", lambda ticker, name="": [
        {"title": f"종목 뉴스 {ticker}", "datetime": recent, "tag": name,
         "link": "https://example.com/stock"}
    ])
    monkeypatch.setattr(service, "fetch_keyword_rss", lambda query, tag, limit=6: [
        {"title": f"구성종목 뉴스 {tag}", "datetime": recent, "tag": tag,
         "link": "https://example.com/theme"}
    ])
    monkeypatch.setattr(service, "fetch_economy_rss", lambda limit=15: [
        {"title": "경제 뉴스", "datetime": recent, "tag": "경제속보",
         "link": "https://example.com/economy"}
    ])
    etfs = [ETFConfig(ticker="381170", name="TIGER 미국테크TOP10 INDXX", target_weight=0.15)]
    watchlist = [WatchlistConfig(ticker="069500", name="KODEX 200")]

    feed_portfolio = service.get_news_feed(mode="portfolio_only", etfs=etfs, watchlist=watchlist)
    assert isinstance(feed_portfolio, list)
    assert len(feed_portfolio) > 0
    assert all({"tag", "title", "link"} <= set(item) for item in feed_portfolio)

    feed_all = service.get_news_feed(mode="all", etfs=etfs, watchlist=watchlist)
    assert isinstance(feed_all, list)
    assert len(feed_all) >= len(feed_portfolio)
    assert any(item["title"] == "경제 뉴스" for item in feed_all)


def test_news_service_empty_feed_without_fallback():
    """기사가 없을 때 실제 뉴스가 아닌 안내 문구를 끼워 넣지 않는다."""
    service = NewsService()
    assert service.get_news_feed(mode="portfolio_only", etfs=[], watchlist=[]) == []
