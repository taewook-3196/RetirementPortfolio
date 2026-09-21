"""
tests/test_morning_report.py
모닝 모바일 웹 리포트 및 카카오톡 연동 단위 테스트.
"""

import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.config import AppConfig, MorningReportConfig, load_config, save_config, ETFConfig
from services.report_html_generator import ReportHtmlGenerator
from services.kakao_service import KakaoService
from services.daily_report_service import DailyReportService
from database.connection import init_db
from database.repository import Repository


@pytest.fixture
def temp_config_file(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg = AppConfig(
        data_source="mock",
        initial_capital=50000000,
        base_monthly=10000000,
        max_additional_monthly=5000000,
        etfs=[ETFConfig(ticker="069500", name="KODEX 200", target_weight=1.0)],
        morning_report=MorningReportConfig(
            enabled=True,
            send_time="07:00",
            kakao_rest_api_key="test_api_key",
            kakao_access_token="test_access_token",
            kakao_refresh_token="test_refresh_token",
            include_ai_briefing=True,
            include_news=True,
            include_summary=True,
            include_positions=True,
            include_market_indices=True,
        )
    )
    save_config(cfg, cfg_file)
    return cfg_file


def test_morning_report_config_serialization(temp_config_file):
    """MorningReportConfig의 YAML 저장 및 로드 검증"""
    loaded_cfg = load_config(temp_config_file)
    m = loaded_cfg.morning_report

    assert m.enabled is True
    assert m.send_time == "07:00"
    assert m.kakao_rest_api_key == "test_api_key"
    assert m.kakao_access_token == "test_access_token"
    assert m.kakao_refresh_token == "test_refresh_token"
    assert m.include_ai_briefing is True
    assert m.include_news is True
    assert m.include_summary is True


def test_gemini_config_persistence(tmp_path):
    """Gemini API 키 및 모델 설정의 저장 및 재로드 영구 보존 검증"""
    cfg_file = tmp_path / "config.yaml"
    cfg = AppConfig(
        data_source="mock",
        etfs=[ETFConfig(ticker="069500", name="KODEX 200", target_weight=1.0)],
        morning_report=MorningReportConfig(
            gemini_enabled=True,
            gemini_api_key="AIzaSyTestPersistentKey999",
            gemini_model="gemini-3.8-flash",
        )
    )
    save_config(cfg, cfg_file)

    loaded = load_config(cfg_file)
    assert loaded.morning_report.gemini_enabled is True
    assert loaded.morning_report.gemini_api_key == "AIzaSyTestPersistentKey999"
    assert loaded.morning_report.gemini_model == "gemini-3.8-flash"



def test_report_html_generator(tmp_path):
    """모바일 반응형 웹 리포트 HTML 생성 및 조건부 렌더링 검증"""
    cfg = MorningReportConfig(
        include_ai_briefing=True,
        include_news=True,
        include_summary=True,
        include_positions=True,
        include_market_indices=True,
    )
    generator = ReportHtmlGenerator(cfg)

    report_data = {
        "account_name": "신한 IRP 연금",
        "summary": {
            "total_eval": 120000000,
            "total_cost": 100000000,
            "total_pl": 20000000,
            "total_pl_pct": 20.0,
            "cash_balance": 5000000,
        },
        "recommendations": {
            "d_day": 3,
            "next_buy_date": "2026-09-25",
            "cycle_desc": "매월 25일",
            "already_invested_this_month": False,
            "total_recommended_amount": 3000000,
            "items": [
                {
                    "name": "KODEX 200",
                    "ticker": "069500",
                    "recommended_shares": 10,
                    "recommended_amount": 400000,
                    "reason": "목표 비중 부족",
                }
            ],
        },
        "positions": [
            {
                "name": "KODEX 200",
                "ticker": "069500",
                "shares": 100,
                "current_price": 40000,
                "eval_amount": 4000000,
                "pl_pct": 5.2,
                "current_weight": 0.5,
                "target_weight": 0.6,
            }
        ],
        "news": [
            {
                "title": "뉴욕증시 상승 마감",
                "media": "한국경제",
                "date": "2026.09.21",
                "link": "https://example.com/news1",
                "tag": "증시",
            }
        ],
        "market_indices": {
            "KODEX 200": {"price": "40,000원", "change_pct": 1.25}
        },
    }

    out_file = generator.generate_html(report_data, output_filename="test_report.html")
    assert out_file.exists()

    content = out_file.read_text(encoding="utf-8")
    assert "신한 IRP 연금" in content
    assert "120,000,000원" in content
    assert "D-3" in content
    assert "뉴욕증시 상승 마감" in content
    assert "viewport" in content


def test_report_html_generator_conditional_sections():
    """조건부 섹션 On/Off 검증"""
    # AI 브리핑과 뉴스를 끈 경우
    cfg = MorningReportConfig(
        include_ai_briefing=False,
        include_news=False,
        include_summary=True,
        include_positions=True,
    )
    generator = ReportHtmlGenerator(cfg)

    report_data = {
        "account_name": "기본 계좌",
        "summary": {"total_eval": 10000000},
        "recommendations": {"d_day": 0, "items": []},
        "positions": [],
        "news": [{"title": "테스트 뉴스"}],
    }

    out_file = generator.generate_html(report_data, output_filename="test_report_disabled.html")
    content = out_file.read_text(encoding="utf-8")

    assert "AI 투자 가이드" not in content
    assert "테스트 뉴스" not in content
    assert "내 계좌 자산 총괄" in content


def test_kakao_service_without_token():
    """카카오 토큰 부재 시 에러 처리 검증"""
    cfg = AppConfig(
        morning_report=MorningReportConfig(kakao_access_token="")
    )
    kakao = KakaoService(cfg)
    assert not kakao.is_configured()

    ok, msg = kakao.send_morning_report("요약 내용", "http://example.com")
    assert ok is False
    assert "Access Token이 비어있습니다" in msg


def test_daily_report_service_generation(monkeypatch):
    """DailyReportService 오케스트레이터의 HTML 생성 및 카카오 발송 흐름 검증"""
    init_db()
    repo = Repository()

    cfg = AppConfig(
        data_source="mock",
        etfs=[ETFConfig(ticker="069500", name="KODEX 200", target_weight=1.0)],
        morning_report=MorningReportConfig(
            enabled=False,  # 카카오 실제 전송은 비활성화
            include_summary=True,
            include_ai_briefing=True,
            include_news=False,
        )
    )

    service = DailyReportService(config=cfg, repo=repo)
    ok, msg, file_path = service.generate_and_send(send_kakao=False)

    assert ok is True
    assert file_path is not None
    assert file_path.exists()
    assert "성공적" in msg


def test_daily_report_service_updates_prices_before_generation(monkeypatch):
    """리포트 생성 시작 시 update_market_prices 호출 여부 검증"""
    init_db()
    repo = Repository()

    cfg = AppConfig(
        data_source="mock",
        etfs=[ETFConfig(ticker="069500", name="KODEX 200", target_weight=1.0)],
        morning_report=MorningReportConfig(
            enabled=False,
            include_summary=True,
        )
    )

    called = {"count": 0, "days": 0}

    def fake_update_market_prices(config=None, repo=None, days=90, scenario="normal"):
        called["count"] += 1
        called["days"] = days
        return {"status": "success", "data_source": "mock", "saved_count": 1}

    import data.price_updater
    monkeypatch.setattr(data.price_updater, "update_market_prices", fake_update_market_prices)

    service = DailyReportService(config=cfg, repo=repo)
    ok, msg, file_path = service.generate_and_send(send_kakao=False)

    assert ok is True
    assert called["count"] == 1
    assert called["days"] == 5


def test_report_html_generator_multi_account_positions(tmp_path):
    """다중 계좌별 등록 및 보유종목 분리 렌더링 및 탭 생성 검증"""
    cfg = MorningReportConfig(
        include_positions=True,
    )
    generator = ReportHtmlGenerator(cfg)

    report_data = {
        "account_name": "전체 통합 포트폴리오 (2개 계좌)",
        "summary": {"total_eval": 60000000},
        "account_groups": [
            {
                "account_id": 1,
                "account_name": "기본 퇴직연금",
                "broker": "신한투자",
                "total_eval": 40000000,
                "total_cost": 35000000,
                "total_pl": 5000000,
                "total_pl_pct": 14.28,
                "cash_balance": 2000000,
                "positions": [
                    {
                        "name": "KODEX 200",
                        "ticker": "069500",
                        "shares": 100,
                        "current_price": 40000,
                        "eval_amount": 4000000,
                        "pl_pct": 5.0,
                        "current_weight": 0.10,
                        "target_weight": 0.15,
                    }
                ],
            },
            {
                "account_id": 2,
                "account_name": "공격형 위탁",
                "broker": "토스증권",
                "total_eval": 20000000,
                "total_cost": 18000000,
                "total_pl": 2000000,
                "total_pl_pct": 11.11,
                "cash_balance": 500000,
                "positions": [
                    {
                        "name": "TIGER 나스닥100",
                        "ticker": "133690",
                        "shares": 50,
                        "current_price": 100000,
                        "eval_amount": 5000000,
                        "pl_pct": 12.0,
                        "current_weight": 0.25,
                        "target_weight": 0.30,
                    }
                ],
            },
        ],
    }

    out_file = generator.generate_html(report_data, output_filename="test_multi_acc_report.html")
    assert out_file.exists()

    content = out_file.read_text(encoding="utf-8")
    assert "account-tabs" in content
    assert "기본 퇴직연금" in content
    assert "공격형 위탁" in content
    assert "신한투자" in content
    assert "토스증권" in content
    assert "KODEX 200" in content
    assert "TIGER 나스닥100" in content
    assert "filterAccountPositions" in content


def test_report_html_generator_multi_account_ai_briefing(tmp_path):
    """다중 계좌별 AI 투자 가이드 및 매수 전략 분리 렌더링 검증"""
    cfg = MorningReportConfig(
        include_ai_briefing=True,
    )
    generator = ReportHtmlGenerator(cfg)

    report_data = {
        "account_name": "전체 통합 포트폴리오 (2개 계좌)",
        "summary": {"total_eval": 60000000},
        "account_recommendations": [
            {
                "account_id": 1,
                "account_name": "기본 계좌 (퇴직연금)",
                "broker": "신한투자",
                "d_day": 3,
                "next_buy_date": "2026-09-24",
                "cycle_desc": "매월 24일",
                "already_invested_this_month": False,
                "total_recommended_amount": 500000,
                "ai_guide_comment": "안정형 포트폴리오: KODEX 200 비중 확대를 추천합니다.",
                "items": [
                    {
                        "name": "KODEX 200",
                        "ticker": "069500",
                        "current_price": 40000,
                        "recommended_shares": 10,
                        "recommended_amount": 400000,
                        "reason": "목표 비중 부족",
                    }
                ],
            },
            {
                "account_id": 2,
                "account_name": "공격형 위탁 계좌",
                "broker": "토스증권",
                "d_day": -1,
                "next_buy_date": "2026-09-21",
                "cycle_desc": "매주 화요일",
                "already_invested_this_month": True,
                "total_recommended_amount": 0,
                "ai_guide_comment": "이번 주기 매수가 이미 완료되었습니다.",
                "items": [],
            },
        ],
    }

    out_file = generator.generate_html(report_data, output_filename="test_multi_ai_report.html")
    assert out_file.exists()

    content = out_file.read_text(encoding="utf-8")
    assert "ai-tabs" in content
    assert "filterAccountAiGuide" in content
    assert "기본 계좌 (퇴직연금)" in content
    assert "공격형 위탁 계좌" in content
    assert "D-3" in content
    assert "이번 주기 매수 완료" in content
    assert "KODEX 200" in content
    assert "10주" in content
    assert "400,000원" in content
    assert "안정형 포트폴리오: KODEX 200 비중 확대를 추천합니다." in content
    assert "이번 주기 매수가 이미 완료되었습니다." in content


def test_investment_stance_html_and_kakao_rendering():
    """AI 투자 성향 배지가 모바일 HTML 리포트와 카카오톡 요약문에 정상 반영되는지 검증"""
    generator = ReportHtmlGenerator(MorningReportConfig())
    gemini_data = {
        "success": True,
        "model_used": "gemini-3.8-flash",
        "stance_key": "aggressive",
        "stance_label": "공격적",
        "stance_badge": "🚀 공격적",
        "one_line_summary": "단기 조정은 매수 기회입니다.",
        "macro_analysis": "거시경제 분석 내용...",
        "strategy_advice": "전략 조언 내용...",
    }

    # 1. HTML 리포트 검증
    report_data = {
        "summary": {"total_eval": 10000000, "total_cost": 9000000, "total_pl": 1000000, "total_pl_pct": 11.1},
        "gemini_analysis": gemini_data,
        "recommendations": {},
        "positions": [],
        "news": [],
        "market_indices": {},
    }
    out_file = generator.generate_html(report_data, output_filename="test_stance_report.html")
    assert out_file.exists()
    html_content = out_file.read_text(encoding="utf-8")
    assert "🚀 공격적" in html_content
    assert "GEMINI 3.8 FLASH" in html_content
    assert "단기 조정은 매수 기회입니다." in html_content

    # 2. 카카오톡 요약 텍스트 검증
    service = DailyReportService()
    kakao_text = service._build_kakao_summary_text(
        account_name="테스트 계좌",
        summary={"total_eval": 10000000, "total_pl": 1000000, "total_pl_pct": 11.1},
        recommendations={"d_day": 3, "total_recommended_amount": 500000},
        news_items=[],
        gemini_analysis=gemini_data,
    )
    assert "• 🤖 AI 시황 [🚀 공격적]: 단기 조정은 매수 기회입니다." in kakao_text


