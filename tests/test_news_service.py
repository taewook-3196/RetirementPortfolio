"""
tests/test_news_service.py
NewsService 단위 테스트.
- 네이버 모바일 종목 뉴스 및 구글 RSS 뉴스 수집 검증
- ETF 구성종목 매핑 검증
- 필터 모드별 피드 생성 및 중복 제거 검증
"""

import pytest
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


def test_news_service_get_feed_structure():
    """피드 반환 데이터 구조 검증"""
    service = NewsService()
    etfs = [ETFConfig(ticker="381170", name="TIGER 미국테크TOP10 INDXX", target_weight=0.15)]
    watchlist = [WatchlistConfig(ticker="069500", name="KODEX 200")]

    # 1. portfolio_only 모드 테스트
    feed_portfolio = service.get_news_feed(mode="portfolio_only", etfs=etfs, watchlist=watchlist)
    assert isinstance(feed_portfolio, list)
    assert len(feed_portfolio) > 0
    first_item = feed_portfolio[0]
    assert "tag" in first_item
    assert "title" in first_item
    assert "link" in first_item

    # 2. all 모드 테스트 (경제 속보 포함)
    feed_all = service.get_news_feed(mode="all", etfs=etfs, watchlist=watchlist)
    assert isinstance(feed_all, list)
    assert len(feed_all) >= len(feed_portfolio)


def test_news_service_fallback():
    """네트워크 실패 시 안전한 기본값 폴백 검증"""
    service = NewsService()
    # 빈 파라미터로 호출 시 최소한의 피드 반환
    feed = service.get_news_feed(mode="portfolio_only", etfs=[], watchlist=[])
    assert isinstance(feed, list)
    assert len(feed) >= 1
    assert "title" in feed[0]
