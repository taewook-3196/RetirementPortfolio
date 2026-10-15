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


def test_report_assembly_rechecks_news_freshness():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "services" / "daily_report_service.py").read_text(encoding="utf-8")
    assert "for item in filter_recent_news(feed)[:8]:" in source


def test_name_only_watchlist_still_gets_keyword_news(monkeypatch):
    from types import SimpleNamespace

    service = NewsService()
    calls = []
    monkeypatch.setattr(service, "fetch_stock_news", lambda *args: [])

    def keyword_news(query, tag, limit=4):
        calls.append((query, tag))
        return [{"title": "해외 관심종목 최신 기사",
                 "datetime": datetime.now(timezone.utc).isoformat(),
                 "tag": tag}]

    monkeypatch.setattr(service, "fetch_keyword_rss", keyword_news)
    result = service.get_news_feed(mode="portfolio_only",
                                   watchlist=[SimpleNamespace(ticker="", name="엔비디아")])
    assert calls == [("엔비디아", "엔비디아")]
    assert [item["title"] for item in result] == ["해외 관심종목 최신 기사"]


def test_overlapping_portfolio_watchlist_fetches_each_source_once(monkeypatch):
    from types import SimpleNamespace

    service = NewsService()
    stock_calls = []
    keyword_calls = []
    monkeypatch.setattr(service, "fetch_stock_news", lambda ticker, name="": stock_calls.append(ticker) or [])
    monkeypatch.setattr(service, "fetch_keyword_rss", lambda query, tag, limit=4: keyword_calls.append(query) or [])
    asset = SimpleNamespace(ticker="069500", name="코스피 대형주")
    assert service.get_news_feed(mode="portfolio_only", etfs=[asset], watchlist=[asset]) == []
    assert stock_calls == ["069500"]
    assert len(keyword_calls) == 1


def test_same_theme_query_is_fetched_once_for_different_tickers(monkeypatch):
    from types import SimpleNamespace

    service = NewsService()
    keyword_calls = []
    monkeypatch.setattr(service, "fetch_stock_news", lambda ticker, name="": [])
    monkeypatch.setattr(service, "fetch_keyword_rss", lambda query, tag, limit=4: keyword_calls.append(query) or [])
    assets = [SimpleNamespace(ticker="A", name="반도체"), SimpleNamespace(ticker="B", name="반도체")]
    service.get_news_feed(mode="portfolio_only", watchlist=assets)
    assert len(keyword_calls) == 1


def test_news_section_uses_accurate_freshness_label():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "services" / "report_html_generator.py").read_text(encoding="utf-8")
    assert '<span class="badge badge-info">최근 24시간 뉴스</span>' in source
    assert '<span class="badge badge-info">실시간 픽</span>' not in source


def test_news_html_escapes_external_metadata_and_link_attributes():
    from services.report_html_generator import ReportHtmlGenerator

    result = ReportHtmlGenerator()._render_news_section([{
        "title": '<img src=x onerror="alert(1)">',
        "media": "<script>alert(1)</script>",
        "tag": "<b>risk</b>",
        "date": "<svg/onload=alert(1)>",
        "link": 'https://example.com/?q=" onclick="alert(1)',
    }])
    assert "<script>" not in result
    assert "<img src=x" not in result
    assert "<b>risk</b>" not in result
    assert "&lt;svg" in result
    assert 'href="https://example.com/?q=&quot; onclick=&quot;alert(1)"' in result


def test_news_html_rejects_non_http_and_hostless_links():
    from services.report_html_generator import ReportHtmlGenerator

    render = ReportHtmlGenerator()._render_news_section
    for bad in ("javascript:alert(1)", "https:///missing-host", "data:text/html,hello"):
        assert 'href="#"' in render([{"title": "기사", "link": bad}])


def test_news_section_omits_blank_headlines_and_empty_cards():
    from services.report_html_generator import ReportHtmlGenerator

    render = ReportHtmlGenerator()._render_news_section
    assert render([{"title": "  "}, {"title": ""}]) == ""
    result = render([{"title": ""}, {"title": "정상 뉴스", "link": "https://example.com"}])
    assert result.count('class="news-item"') == 1
    assert "정상 뉴스" in result
