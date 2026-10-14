"""Ensure Morning Report never displays stale or undated news."""

from datetime import datetime, timedelta, timezone

from services.news_service import NewsService, filter_recent_news, parse_news_published_at


NOW = datetime(2026, 10, 14, 1, 0, tzinfo=timezone.utc)


def test_news_timestamp_formats():
    assert parse_news_published_at("Wed, 14 Oct 2026 00:30:00 GMT") == datetime(
        2026, 10, 14, 0, 30, tzinfo=timezone.utc
    )
    assert parse_news_published_at("2026-10-14T09:30:00+09:00") == datetime(
        2026, 10, 14, 0, 30, tzinfo=timezone.utc
    )
    assert parse_news_published_at("2026.10.14 09:30") == datetime(
        2026, 10, 14, 0, 30, tzinfo=timezone.utc
    )
    assert parse_news_published_at("20261014093000") == datetime(
        2026, 10, 14, 0, 30, tzinfo=timezone.utc
    )
    assert parse_news_published_at("") is None
    assert parse_news_published_at("yesterday") is None


def test_recent_news_excludes_stale_future_and_unknown_and_sorts():
    items = [
        {"title": "old", "datetime": (NOW - timedelta(hours=24, seconds=1)).isoformat()},
        {"title": "recent", "datetime": (NOW - timedelta(hours=2)).isoformat()},
        {"title": "unknown", "datetime": ""},
        {"title": "boundary", "datetime": (NOW - timedelta(hours=24)).isoformat()},
        {"title": "future", "datetime": (NOW + timedelta(seconds=1)).isoformat()},
        {"title": "latest", "datetime": (NOW - timedelta(minutes=5)).isoformat()},
    ]
    assert [x["title"] for x in filter_recent_news(items, now=NOW)] == [
        "latest", "recent", "boundary"
    ]


def test_empty_feed_does_not_insert_fake_news(monkeypatch):
    service = NewsService()
    monkeypatch.setattr(service, "fetch_economy_rss", lambda limit=15: [])
    assert service.get_news_feed(mode="all") == []


def test_all_sources_use_same_cutoff(monkeypatch):
    service = NewsService()
    stale = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    fresh = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    monkeypatch.setattr(service, "fetch_stock_news", lambda ticker, name="": [
        {"title": "stale stock", "datetime": stale},
        {"title": "fresh stock", "datetime": fresh},
    ])
    monkeypatch.setattr(service, "fetch_keyword_rss", lambda *args, **kwargs: [
        {"title": "stale theme", "datetime": stale},
    ])
    monkeypatch.setattr(service, "fetch_economy_rss", lambda limit=15: [
        {"title": "stale economy", "datetime": stale},
    ])
    class Asset:
        ticker = "069500"
        name = "KOSPI"
    assert [x["title"] for x in service.get_news_feed(etfs=[Asset()])] == [
        "fresh stock"
    ]


def test_stale_duplicate_cannot_hide_fresh_article(monkeypatch):
    service = NewsService()
    old = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    recent = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    headline = "같은 회사 실적 발표 뉴스"
    monkeypatch.setattr(service, "fetch_stock_news", lambda ticker, name="": [
        {"title": headline, "datetime": old, "link": "https://example.com/old"}
    ])
    monkeypatch.setattr(service, "fetch_keyword_rss", lambda *args, **kwargs: [
        {"title": headline, "datetime": recent, "link": "https://example.com/fresh"}
    ])
    class Asset:
        ticker = "069500"
        name = "KOSPI"
    result = service.get_news_feed(mode="portfolio_only", etfs=[Asset()])
    assert len(result) == 1
    assert result[0]["link"] == "https://example.com/fresh"


def test_newest_duplicate_wins_even_if_collected_later(monkeypatch):
    service = NewsService()
    older = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat()
    newer = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
    headline = "중복 기사 제목"
    monkeypatch.setattr(service, "fetch_stock_news", lambda ticker, name="": [
        {"title": headline, "datetime": older, "link": "https://example.com/older"}
    ])
    monkeypatch.setattr(service, "fetch_keyword_rss", lambda *args, **kwargs: [
        {"title": headline, "datetime": newer, "link": "https://example.com/newer"}
    ])
    class Asset:
        ticker = "069500"
        name = "KOSPI"
    result = service.get_news_feed(mode="portfolio_only", etfs=[Asset()])
    assert len(result) == 1
    assert result[0]["link"] == "https://example.com/newer"


def test_duplicate_titles_ignore_whitespace_and_punctuation(monkeypatch):
    service = NewsService()
    older = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    newer = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    monkeypatch.setattr(service, "fetch_stock_news", lambda ticker, name="": [
        {"title": "삼성전자, 실적 발표!", "datetime": older,
         "link": "https://example.com/older"}
    ])
    monkeypatch.setattr(service, "fetch_keyword_rss", lambda *args, **kwargs: [
        {"title": "삼성전자 실적발표", "datetime": newer,
         "link": "https://example.com/newer"}
    ])
    class Asset:
        ticker = "069500"
        name = "KOSPI"
    result = service.get_news_feed(mode="portfolio_only", etfs=[Asset()])
    assert len(result) == 1
    assert result[0]["link"] == "https://example.com/newer"
