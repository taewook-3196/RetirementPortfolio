"""정적 아침 보고서의 인라인 차트와 관리 링크 회귀 테스트."""

import json
import re
import datetime
from unittest.mock import Mock

from core.config import DEFAULT_WEB_APP_URL, MorningReportConfig, get_web_app_url
from services.daily_report_service import DailyReportService
from services.report_html_generator import ReportHtmlGenerator


def _chart_data():
    return {
        "prices": [
            {
                "date": "2026-09-29",
                "open": 100,
                "high": 106,
                "low": 99,
                "close": 104,
            },
            {
                "date": "2026-09-30",
                "open": 104,
                "high": 109,
                "low": 102,
                "close": 108,
            },
        ],
        "transactions": [
            {"date": "2026-09-29", "type": "BUY", "price": 101, "quantity": 2},
            {"date": "2026-09-30", "type": "SELL", "price": 107, "quantity": 1},
        ],
    }


def _report_data(chart_data):
    position = {
        "ticker": "AAA",
        "name": "차트 종목",
        "currency": "KRW",
        "shares": 1,
        "current_price": 108,
        "eval_amount": 108,
        "pl_pct": 6.93,
        "current_weight": 1.0,
        "target_weight": 1.0,
        "chart_data": chart_data,
    }
    return {
        "account_name": "테스트 계좌",
        "summary": {},
        "positions": [dict(position, account_id=7)],
        "account_groups": [
            {
                "account_id": 7,
                "account_name": "테스트 계좌",
                "currency": "KRW",
                "positions": [position],
            }
        ],
        "portfolio_management_url": "https://portfolio.example/app/",
    }


def _generate(monkeypatch, tmp_path, chart_data):
    monkeypatch.setattr(
        "services.report_html_generator.get_report_dir",
        lambda: tmp_path,
    )
    generator = ReportHtmlGenerator(
        MorningReportConfig(
            include_summary=False,
            include_ai_briefing=False,
            include_news=False,
            include_market_indices=False,
        )
    )
    path = generator.generate_html(
        _report_data(chart_data),
        output_filename="report.html",
    )
    return path.read_text(encoding="utf-8")


def test_report_contains_collapsible_chart_data_and_deep_link(monkeypatch, tmp_path):
    content = _generate(monkeypatch, tmp_path, _chart_data())

    assert 'class="report-chart-toggle"' in content
    assert 'aria-expanded="false"' in content
    assert "toggleReportChart(this)" in content
    for period in ("1M", "3M", "6M", "1Y", "ALL"):
        assert f'data-period="{period}"' in content
    assert "BUY ▲" in content
    assert "SELL ▼" in content
    assert "?account=7&amp;ticker=AAA" in content

    match = re.search(
        r'<script id="report-chart-data" type="application/json">(.*?)</script>',
        content,
        re.DOTALL,
    )
    assert match is not None
    payload = json.loads(match.group(1))
    assert payload["7:AAA"]["prices"][1]["close"] == 108
    assert payload["7:AAA"]["transactions"] == _chart_data()["transactions"]


def test_report_has_management_link_and_does_not_embed_secrets(
    monkeypatch,
    tmp_path,
):
    secrets = {
        "SUPABASE_ACCESS_TOKEN": "secret-access-token",
        "SUPABASE_REFRESH_TOKEN": "secret-refresh-token",
        "DATABASE_URL": "postgresql://secret-db",
        "GEMINI_API_KEY": "secret-gemini-key",
        "KAKAO_ACCESS_TOKEN": "secret-kakao-token",
    }
    for key, value in secrets.items():
        monkeypatch.setenv(key, value)

    content = _generate(monkeypatch, tmp_path, _chart_data())

    assert "계좌 · 거래 관리" in content
    assert 'href="https://portfolio.example/app/"' in content
    for value in secrets.values():
        assert value not in content


def test_management_url_uses_validated_environment_setting(monkeypatch):
    monkeypatch.setenv(
        "RETIREMENT_PORTFOLIO_WEB_URL",
        "https://custom.example/manage",
    )
    assert get_web_app_url() == "https://custom.example/manage/"

    monkeypatch.setenv(
        "RETIREMENT_PORTFOLIO_WEB_URL",
        "javascript:alert(1)",
    )
    assert get_web_app_url() == DEFAULT_WEB_APP_URL


def test_missing_chart_data_keeps_report_and_fallback_link(monkeypatch, tmp_path):
    content = _generate(monkeypatch, tmp_path, {})

    assert "차트 종목" in content
    assert "표시할 가격 데이터가 없습니다." in content
    assert "웹앱 상세보기" in content
    assert "?account=7&amp;ticker=AAA" in content


def test_daily_report_sanitizes_and_limits_embedded_chart_data():
    prices = [
        {
            "date": f"2026-09-{day:02d}",
            "open": day,
            "high": day + 2,
            "low": day - 1,
            "close": day + 1,
            "volume": 999,
        }
        for day in range(1, 6)
    ]
    repo = Mock()
    repo.get_asset_chart_data.return_value = {
        "prices": prices,
        "transactions": [
            {
                "id": 55,
                "date": "2026-09-03",
                "type": "BUY",
                "price": 3,
                "quantity": 2,
                "memo": "보고서에 포함하지 않음",
            }
        ],
    }
    service = DailyReportService(repo=repo)
    groups = [
        {
            "account_id": 7,
            "positions": [{"ticker": "AAA"}],
        }
    ]

    service._attach_report_chart_data(groups, price_limit=3)

    embedded = groups[0]["positions"][0]["chart_data"]
    repo.get_asset_chart_data.assert_called_once_with(
        account_id=7,
        ticker="AAA",
        limit=3,
    )
    assert len(embedded["prices"]) == 3
    assert set(embedded["prices"][0]) == {"date", "open", "high", "low", "close"}
    assert embedded["transactions"] == [
        {"date": "2026-09-03", "type": "BUY", "price": 3.0, "quantity": 2.0}
    ]
    assert "memo" not in json.dumps(embedded, ensure_ascii=False)
    assert "id" not in embedded["transactions"][0]


def test_private_report_generation_does_not_create_pages_index(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        "services.report_html_generator.get_report_dir",
        lambda: tmp_path,
    )
    monkeypatch.setenv("GITHUB_SHA", "abcdef1234567890")
    date_key = datetime.datetime.now().strftime("%Y%m%d")
    generator = ReportHtmlGenerator(
        MorningReportConfig(
            include_summary=False,
            include_ai_briefing=False,
            include_news=False,
            include_market_indices=False,
        )
    )
    generator.generate_html(
        _report_data(_chart_data()),
        output_filename=f"morning_report_{date_key}.html",
    )

    dated = tmp_path / f"morning_report_{date_key}.html"
    assert dated.is_file()
    assert 'name="report-build" content="abcdef123456"' in dated.read_text(encoding="utf-8")
    assert not (tmp_path / "index.html").exists()
