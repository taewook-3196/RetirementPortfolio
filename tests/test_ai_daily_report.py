"""아침 보고서 AI 입력, 응답 및 장애 격리 테스트."""

import json
from unittest.mock import Mock

import pytest

from core.config import MorningReportConfig
from services.daily_report_service import DailyReportService
from services.gemini_service import GeminiService
from services.report_html_generator import ReportHtmlGenerator


def _context():
    return {
        "account_name": "통합 포트폴리오",
        "summary": {
            "total_assets": 1_500_000,
            "stock_eval": 900_000,
            "cash_balance": 600_000,
            "total_cost": 800_000,
            "total_pl": 120_000,
            "total_pl_pct": 15.0,
        },
        "account_groups": [
            {
                "account_id": 1,
                "account_name": "연금 계좌",
                "currency": "KRW",
                "total_eval": 900_000,
                "cash_balance": 600_000,
                "total_assets": 1_500_000,
                "total_cost": 800_000,
                "total_pl": 120_000,
            }
        ],
        "positions": [
            {
                "ticker": "ETF1",
                "shares": 10,
                "average_buy_price": 80_000,
                "current_price": 90_000,
                "total_buy_cost": 800_000,
                "eval_amount": 900_000,
                "unrealized_pnl": 100_000,
                "realized_pnl": 10_000,
                "dividends": 10_000,
                "total_pnl": 120_000,
                "current_weight": 0.60,
                "target_weight": 0.70,
            }
        ],
        "account_recommendations": [
            {
                "account_id": 1,
                "items": [
                    {
                        "ticker": "ETF1",
                        "available_buy_budget": 50_000,
                        "available_buy_shares": 0,
                        "executable_buy_amount": 0,
                    }
                ],
            }
        ],
        "recommendations": {"total_recommended_amount": 50_000},
        "recent_transactions": [
            {"ticker": "ETF1", "type": "BUY", "quantity": 2, "price": 85_000}
        ],
        "news": [{"title": "보유 ETF 관련 뉴스", "media": "테스트뉴스"}],
        "watchlist": [{"ticker": "WATCH1", "name": "관심 종목"}],
        "market_indices": {"KOSPI": {"price": "2,700", "change_pct": 0.5}},
        "macro_summary": "미국 시장과 국내 시장 데이터 요약",
        "macro_indicators": {
            "raw_items": {"usd_krw": {"price_str": "1,350.0원"}}
        },
        "investment_profile": {
            "investment_preference_text": "급등 시 추격매수하지 않고 분할매수한다."
        },
    }


def _valid_response():
    return json.dumps(
        {
            "action": "HOLD",
            "one_line_summary": "시장 데이터와 기존 계획을 함께 확인하세요.",
            "macro_analysis": "제공된 시장 데이터 기준으로 변동성을 확인해야 합니다.",
            "portfolio_status": "현금과 주식평가액은 입력 데이터 기준입니다.",
            "strategy_advice": "시스템 추천 범위 안에서 기존 계획을 유지하세요.",
            "risk_checks": "환율 변동과 데이터 기준시점을 확인하세요.",
        },
        ensure_ascii=False,
    )


def test_normal_ai_response_and_verified_prompt_data():
    service = GeminiService(api_key="secret-test-key")
    captured = {}

    def fake_call(**kwargs):
        captured["prompt"] = kwargs["prompt"]
        return True, "gemini-test", _valid_response()

    service._call_gemini_api = fake_call
    result = service.generate_macro_investment_guide(_context())
    prompt = captured["prompt"]

    assert result["success"] is True
    assert result["model_used"] == "gemini-test"
    assert '"total_assets": 1500000' in prompt
    assert '"shares": 10' in prompt
    assert '"average_buy_price": 80000' in prompt
    assert '"cash_balance": 600000' in prompt
    assert '"available_buy_budget": 50000' in prompt
    assert '"recent_transactions"' in prompt
    assert "보유 ETF 관련 뉴스" in prompt
    assert "WATCH1" in prompt
    assert "급등 시 추격매수하지 않고 분할매수한다." in prompt
    assert "별도의 금액이나 수량을 새로 계산" in prompt
    assert "secret-test-key" not in prompt

    html = ReportHtmlGenerator(MorningReportConfig())._render_gemini_section(
        result
    )
    assert "오늘 시장 핵심 요약" in html
    assert "내 포트폴리오 상태" in html
    assert "현재 매수전략 관련 참고사항" in html
    assert "주요 위험요인/확인할 사항" in html


def test_missing_api_key_returns_fallback():
    result = GeminiService(api_key="").generate_macro_investment_guide(_context())

    assert result["success"] is False
    assert "API 키" in result["error"]
    assert result["one_line_summary"]


@pytest.mark.parametrize("exception", [TimeoutError(), RuntimeError("network")])
def test_timeout_and_api_exception_return_fallback(exception):
    service = GeminiService(api_key="secret-test-key")
    service._call_gemini_api = Mock(side_effect=exception)

    result = service.generate_macro_investment_guide(_context())

    assert result["success"] is False
    assert result["one_line_summary"]


@pytest.mark.parametrize("raw_response", ["", "잘못된 일반 텍스트 응답"])
def test_empty_or_invalid_response_returns_fallback(raw_response):
    service = GeminiService(api_key="secret-test-key")
    service._call_gemini_api = Mock(
        return_value=(True, "gemini-test", raw_response)
    )

    result = service.generate_macro_investment_guide(_context())

    assert result["success"] is False
    assert "응답" in result["error"]


def test_ai_failure_is_rendered_without_exposing_api_key(caplog):
    secret = "do-not-expose-this-api-key"
    gemini = GeminiService(api_key=secret)
    gemini.generate_macro_investment_guide = Mock(side_effect=TimeoutError())

    daily = object.__new__(DailyReportService)
    daily.gemini_service = gemini
    fallback = daily._generate_ai_analysis(_context(), enabled=True)

    generator = ReportHtmlGenerator(MorningReportConfig())
    html = generator._render_gemini_section(fallback)
    kakao = daily._build_kakao_summary_text(
        account_name="통합 포트폴리오",
        summary=_context()["summary"],
        recommendations={},
        news_items=[],
        gemini_analysis=fallback,
    )

    assert fallback["success"] is False
    assert "AI 투자분석" in html
    assert "AI 투자분석" in kakao
    assert secret not in html
    assert secret not in kakao
    assert secret not in caplog.text


def test_failed_api_error_text_cannot_leak_api_key_to_log(caplog):
    secret = "do-not-log-this-api-key"
    service = GeminiService(api_key=secret)
    service._call_gemini_api = Mock(
        return_value=(False, "gemini-test", secret)
    )

    result = service.generate_macro_investment_guide(_context())

    assert result["success"] is False
    assert secret not in caplog.text
