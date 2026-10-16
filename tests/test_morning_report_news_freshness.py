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
    assert "for item in filter_recent_news(feed):" in source
    assert 'if len(news_items) >= 8:' in source


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


def test_news_card_limit_counts_only_rendered_headlines():
    from services.report_html_generator import ReportHtmlGenerator

    news = [{"title": "  "}] * 4 + [{"title": f"기사 {i}"} for i in range(10)]
    result = ReportHtmlGenerator()._render_news_section(news)
    assert result.count('class="news-item"') == 8
    assert "기사 7" in result
    assert "기사 8" not in result


def test_report_assembly_skips_blank_headlines_before_limit():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "services" / "daily_report_service.py").read_text(encoding="utf-8")
    assert 'for item in filter_recent_news(feed):' in source
    assert 'if not str(item.get("title", "") or "").strip():' in source
    assert 'if len(news_items) >= 8:' in source


def test_news_feed_ignores_malformed_headlines_and_case_duplicates(monkeypatch):
    from datetime import datetime, timezone

    service = NewsService()
    stamp = datetime.now(timezone.utc).isoformat()
    articles = [
        {"title": None, "datetime": stamp},
        {"title": 123, "datetime": stamp},
        {"title": "  ", "datetime": stamp},
        {"title": "Market Rally", "datetime": stamp},
        {"title": "market rally", "datetime": stamp},
    ]
    monkeypatch.setattr(service, "fetch_economy_rss", lambda limit=15: articles)
    result = service.get_news_feed(mode="all")
    assert [item["title"] for item in result] == ["Market Rally"]


def test_naver_news_skips_malformed_entries_but_keeps_valid(monkeypatch):
    import io
    import json
    import urllib.request

    service = NewsService()
    payload = [{"items": [None, "broken", {"title": 123}, {"title": "정상 기사", "datetime": "2026-10-15T09:00:00+09:00"}]}]

    class FakeResponse(io.BytesIO):
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.close()

    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: FakeResponse(json.dumps(payload).encode("utf-8")))
    result = service.fetch_stock_news("005930", "삼성전자")
    assert [item["title"] for item in result] == ["정상 기사"]



def test_naver_news_skips_invalid_containers_and_accepts_titlefull(monkeypatch):
    import io
    import json
    import urllib.request

    service = NewsService()
    payload = [
        {"items": None},
        {"items": "invalid"},
        {"titleFull": "정상 제목", "datetime": "2026-10-15T09:00:00+09:00"},
        {"items": [{"title": "다른 정상 기사"}]},
    ]

    class FakeResponse(io.BytesIO):
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.close()

    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: FakeResponse(json.dumps(payload).encode("utf-8")))
    result = service.fetch_stock_news("005930")
    assert [item["title"] for item in result] == ["정상 제목", "다른 정상 기사"]


def test_naver_news_rejects_nonlist_top_level_items(monkeypatch):
    import io
    import json
    import urllib.request

    service = NewsService()

    class FakeResponse(io.BytesIO):
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.close()

    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: FakeResponse(json.dumps({"items": {"title": "invalid"}}).encode("utf-8")))
    assert service.fetch_stock_news("005930") == []


def test_freshness_filter_skips_non_mapping_entries():
    from datetime import datetime, timezone
    from services.news_service import filter_recent_news

    now = datetime.now(timezone.utc)
    valid = {"title": "정상 기사", "datetime": now.isoformat()}
    assert filter_recent_news([None, "broken", 123, valid], now=now) == [valid]



def test_rss_limits_count_valid_articles_not_blank_headlines(monkeypatch):
    import io
    import urllib.request

    service = NewsService()
    xml = """<rss><channel>
      <item><title>  </title></item>
      <item><title>첫 기사 - 매체</title><pubDate>Thu, 15 Oct 2026 01:00:00 GMT</pubDate></item>
      <item><title>둘째 기사</title></item>
      <item><title>셋째 기사</title></item>
    </channel></rss>"""

    class FakeResponse(io.BytesIO):
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.close()

    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: FakeResponse(xml.encode("utf-8")))
    economy = service.fetch_economy_rss(limit=2)
    keyword = service.fetch_keyword_rss("반도체", "테마", limit=2)
    assert [item["title"] for item in economy] == ["첫 기사", "둘째 기사"]
    assert [item["title"] for item in keyword] == ["첫 기사", "둘째 기사"]



def test_rss_nonpositive_limits_do_not_fetch(monkeypatch):
    import urllib.request

    service = NewsService()

    def unexpected_fetch(*args, **kwargs):
        raise AssertionError("RSS fetch must not run for a nonpositive limit")

    monkeypatch.setattr(urllib.request, "urlopen", unexpected_fetch)
    for limit in (0, -1):
        assert service.fetch_economy_rss(limit=limit) == []
        assert service.fetch_keyword_rss("반도체", "테마", limit=limit) == []



def test_naver_twelve_digit_timestamp_is_korean_local_time():
    assert parse_news_published_at("202610160812") == datetime(
        2026, 10, 15, 23, 12, tzinfo=timezone.utc
    )


def test_report_news_decodes_entities_and_formats_dates():
    from services.report_html_generator import ReportHTMLGenerator
    from html import unescape
    from unittest.mock import Mock

    generator = ReportHTMLGenerator.__new__(ReportHTMLGenerator)
    rendered = generator._render_news_section([
        {"title": "&#x27;임상&#x27; &amp;quot;성과&amp;quot; &lt;script&gt;",
         "media": "약업신문", "date": "Thu, 15 Oct 2026 23:03:00 GMT", "tag": "바이오"},
        {"title": "&#x27;최소 329만원&#x27; 아이폰", "media": "이데일리",
         "date": "202610160812", "tag": "삼성전자"},
    ])
    assert "&#x27;임상&#x27;" not in rendered
    assert "&amp;quot;" not in rendered
    assert "'임상'" in unescape(rendered)
    assert '"성과"' in unescape(rendered)
    assert "&lt;script&gt;" in rendered
    assert "<script>" not in rendered
    assert "2026-10-16 08:03" in rendered
    assert "2026-10-16 08:12" in rendered
