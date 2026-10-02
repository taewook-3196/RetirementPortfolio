"""아침 보고서의 자산 금액 집계 및 표시 회귀 테스트."""

from types import SimpleNamespace

import pytest

from core.config import MorningReportConfig
from services.daily_report_service import DailyReportService
from services.report_html_generator import ReportHtmlGenerator


@pytest.fixture
def account_groups():
    return [
        {
            "account_id": 1,
            "account_name": "KRW 현금형 계좌",
            "name": "KRW 현금형 계좌",
            "broker": "KR Broker",
            "currency": "KRW",
            "total_eval": 400_000.0,
            "cash_balance": 600_000.0,
            "total_assets": 1_000_000.0,
            "total_cost": 300_000.0,
            "total_pl": 100_000.0,
            "total_pl_pct": 100_000 / 300_000 * 100,
            "positions": [],
        },
        {
            "account_id": 2,
            "account_name": "USD 현금형 계좌",
            "name": "USD 현금형 계좌",
            "broker": "US Broker",
            "currency": "USD",
            "total_eval": 200.0,
            "cash_balance": 800.0,
            "total_assets": 1_000.0,
            "total_cost": 150.0,
            "total_pl": 50.0,
            "total_pl_pct": 50 / 150 * 100,
            "positions": [],
        },
    ]


def _daily_report_service():
    service = object.__new__(DailyReportService)
    return service


def _overall_portfolio_summary():
    # KRW 계좌 + USD 계좌(1 USD = 1,350 KRW)가 PortfolioService에서
    # 이미 KRW로 통합된 결과입니다.
    return SimpleNamespace(
        currency="KRW",
        total_current_value=670_000.0,
        remaining_cash=1_680_000.0,
        total_invested=502_500.0,
        total_pnl=167_500.0,
        total_roi=167_500 / 502_500,
    )


def test_overall_report_summary_converts_accounts_to_krw(account_groups):
    service = _daily_report_service()

    summary = service._build_overall_portfolio_summary(
        _overall_portfolio_summary()
    )

    assert summary["stock_eval"] == 670_000.0
    assert summary["cash_balance"] == 1_680_000.0
    assert summary["total_cost"] == 502_500.0
    assert summary["total_assets"] == 2_350_000.0
    assert summary["total_eval"] == 2_350_000.0
    assert summary["total_pl"] == 167_500.0
    assert summary["total_pl_pct"] == pytest.approx(33.3333333333)
    assert (
        summary["total_assets"]
        == summary["stock_eval"] + summary["cash_balance"]
    )


def test_html_displays_total_stock_cash_cost_and_account_currencies(
    account_groups,
):
    service = _daily_report_service()
    summary = service._build_overall_portfolio_summary(
        _overall_portfolio_summary()
    )
    generator = ReportHtmlGenerator(MorningReportConfig())

    summary_html = generator._render_summary_section(
        summary,
        account_groups,
    )
    account_html = generator._render_positions_section(
        [],
        account_groups=account_groups,
    )

    assert "총자산" in summary_html
    assert "2,350,000원" in summary_html
    assert "주식평가액" in summary_html
    assert "670,000원" in summary_html
    assert "예수금 (현금 잔고)" in summary_html
    assert "1,680,000원" in summary_html
    assert "주식 매수원가" in summary_html
    assert "502,500원" in summary_html
    assert "총손익:" in summary_html

    assert "KRW 현금형 계좌" in account_html
    assert "총자산" in account_html
    assert "1,000,000원" in account_html
    assert "주식평가액 400,000원" in account_html
    assert "예수금 600,000원" in account_html
    assert "매수원가 300,000원" in account_html

    assert "USD 현금형 계좌" in account_html
    assert "$1,000.00" in account_html
    assert "주식평가액 $200.00" in account_html
    assert "예수금 $800.00" in account_html
    assert "매수원가 $150.00" in account_html


def test_kakao_uses_total_assets_and_preserves_account_currency(account_groups):
    service = _daily_report_service()
    summary = service._build_overall_portfolio_summary(
        _overall_portfolio_summary()
    )

    text = service._build_kakao_summary_text(
        account_name="전체 통합 포트폴리오 (2개 계좌)",
        summary=summary,
        recommendations={},
        news_items=[],
        account_summaries=account_groups,
        account_groups=account_groups,
    )

    assert "• 총자산: 2,350,000원" in text
    assert "• 주식평가액: 670,000원" in text
    assert "• 예수금: 1,680,000원" in text
    assert "• 주식 매수원가: 502,500원" in text
    assert "• 총손익: +167,500원" in text
    assert "KRW 현금형 계좌 1,000,000원" in text
    assert "USD 현금형 계좌 $1,000.00" in text
    assert "USD 현금형 계좌 $200.00" not in text
