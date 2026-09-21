"""
tests/test_macro_indicators.py
모닝 리포트용 10대 글로벌 매크로 지표 수집 및 5일 트렌드 분석 서비스 단위 테스트.
- 1. 미국 증시 3대 지수: S&P500, Nasdaq 100, DOW
- 2. 국내 증시 2대 지수: KOSPI, KOSDAQ
- 3. 거시경제 핵심 3종: 국제 유가(WTI), 미국 10년물 국채금리, 원/달러 환율
- 4. 미국 펀더멘털 지표 2종: 근원 PCE 물가지수, 고용지표 (NFP & 실업률)
- 트렌드 판별 로직, Gemini 요약 문자열, 카카오톡 메시지, 모바일 HTML 렌더링 검증
"""

import pytest
from services.macro_indicator_service import MacroIndicatorService, YAHOO_SYMBOLS, US_ECONOMIC_INDICATORS
from services.report_html_generator import ReportHtmlGenerator
from services.daily_report_service import DailyReportService
from core.config import MorningReportConfig, AppConfig


def test_symbols_and_fundamentals_defined():
    """10대 필수 매크로 지표 정의 확인"""
    # 1. 미국 3대
    assert "sp500" in YAHOO_SYMBOLS
    assert "nasdaq100" in YAHOO_SYMBOLS
    assert "dow" in YAHOO_SYMBOLS

    # 2. 국내 2대
    assert "kospi" in YAHOO_SYMBOLS
    assert "kosdaq" in YAHOO_SYMBOLS

    # 3. 환율, 유가, 국채금리
    assert "usd_krw" in YAHOO_SYMBOLS
    assert "wti_oil" in YAHOO_SYMBOLS
    assert "us10y_yield" in YAHOO_SYMBOLS

    # 4. 미국 펀더멘털 지표 (PCE & 고용)
    assert "core_pce" in US_ECONOMIC_INDICATORS
    assert "jobs_nfp" in US_ECONOMIC_INDICATORS
    assert "unemployment_rate" in US_ECONOMIC_INDICATORS


def test_trend_calculation_logic():
    """5일 종가 히스토리 기반 트렌드(상승/하락/보합) 판별 검증"""
    svc = MacroIndicatorService()

    # 1. 강한 상승 (+2.0%)
    trend, badge, pct = svc._calculate_trend(102.0, [100.0, 100.5, 101.0, 101.5, 102.0], 0.5)
    assert trend == "UP"
    assert "강한 상승" in badge
    assert pct == pytest.approx(2.0, abs=0.01)

    # 2. 완만한 상승 (+0.8%)
    trend, badge, pct = svc._calculate_trend(100.8, [100.0, 100.2, 100.5, 100.6, 100.8], 0.2)
    assert trend == "UP"
    assert "상승 추세" in badge
    assert pct == pytest.approx(0.8, abs=0.01)

    # 3. 강한 하락 (-2.5%)
    trend, badge, pct = svc._calculate_trend(97.5, [100.0, 99.5, 99.0, 98.0, 97.5], -0.5)
    assert trend == "DOWN"
    assert "하락 추세" in badge
    assert pct == pytest.approx(-2.5, abs=0.01)

    # 4. 횡보/보합 (+0.1%)
    trend, badge, pct = svc._calculate_trend(100.1, [100.0, 100.2, 99.9, 100.0, 100.1], 0.1)
    assert trend == "FLAT"
    assert "횡보/보합" in badge

    # 5. 히스토리 부족 시 당일 등락률 기준 폴백
    trend, badge, pct = svc._calculate_trend(100.0, [], 1.2)
    assert trend == "UP"
    assert "상승 추세" in badge

    trend, badge, pct = svc._calculate_trend(100.0, [], -1.0)
    assert trend == "DOWN"
    assert "하락 추세" in badge

    trend, badge, pct = svc._calculate_trend(100.0, [], 0.1)
    assert trend == "FLAT"
    assert "보합세" in badge


def test_format_price():
    """가격 및 단위 문자열 포맷팅 검증"""
    svc = MacroIndicatorService()
    assert svc._format_price(1335.5, "원", 1) == "1,335.5원"
    assert svc._format_price(71.25, "$", 2) == "$71.25"
    assert svc._format_price(3.725, "%", 2) == "3.73%"
    assert svc._format_price(5850.12, "pt", 2) == "5,850.12 pt"


def test_build_summary_for_gemini():
    """Gemini AI 전달용 매크로 텍스트 생성 검증"""
    svc = MacroIndicatorService()
    mock_macro_data = {
        "raw_items": {
            "sp500": {"price_str": "5,873.12 pt", "change_str": "+0.45%", "trend_badge": "▲ 상승 추세 (+1.2%)"},
            "nasdaq100": {"price_str": "20,123.45 pt", "change_str": "+0.80%", "trend_badge": "▲ 강한 상승 (+2.1%)"},
            "dow": {"price_str": "42,063.36 pt", "change_str": "+0.09%", "trend_badge": "━ 횡보/보합 (+0.1%)"},
            "kospi": {"price_str": "2,593.37 pt", "change_str": "+0.21%", "trend_badge": "▲ 상승 추세 (+0.7%)"},
            "kosdaq": {"price_str": "748.30 pt", "change_str": "-0.15%", "trend_badge": "▼ 완만한 하락 (-0.5%)"},
            "usd_krw": {"price_str": "1,332.5원", "change_str": "-0.32%", "trend_badge": "▼ 완만한 하락 (-0.6%)"},
            "wti_oil": {"price_str": "$71.47", "change_str": "-0.28%", "trend_badge": "▼ 완만한 하락 (-0.8%)"},
            "us10y_yield": {"price_str": "3.73%", "change_str": "-0.02%p", "trend_badge": "▼ 완만한 하락 (-0.05%p)"},
        },
        "fundamentals": US_ECONOMIC_INDICATORS,
    }

    summary_text = svc.build_summary_for_gemini(mock_macro_data)
    assert "S&P 500" in summary_text
    assert "Nasdaq 100" in summary_text
    assert "Dow Jones" in summary_text
    assert "코스피" in summary_text
    assert "코스닥" in summary_text
    assert "원/달러 환율" in summary_text
    assert "WTI 국제유가" in summary_text
    assert "미국 10년물 국채금리" in summary_text
    assert "근원 PCE" in summary_text
    assert "비농업 신규고용" in summary_text
    assert "미국 실업률" in summary_text
    assert "▲ 상승 추세" in summary_text


def test_build_kakao_macro_lines():
    """카카오톡 모닝 브리핑용 요약 라인 생성 검증"""
    svc = MacroIndicatorService()
    mock_macro_data = {
        "raw_items": {
            "sp500": {"price": 5873.12, "change_str": "+0.45%"},
            "nasdaq100": {"price": 20123.45, "change_str": "+0.80%"},
            "kospi": {"price": 2593.37, "change_str": "+0.21%", "trend_badge": "▲상승"},
            "usd_krw": {"price": 1332.5},
            "wti_oil": {"price": 71.47},
            "us10y_yield": {"price": 3.73},
        },
        "fundamentals": US_ECONOMIC_INDICATORS,
    }

    lines = svc.build_kakao_macro_lines(mock_macro_data)
    full_text = "\n".join(lines)
    assert "글로벌 10대 지표 & 최근 트렌드" in full_text
    assert "S&P" in full_text
    assert "코스피" in full_text
    assert "환율" in full_text
    assert "PCE" in full_text
    assert "고용" in full_text


def test_html_generator_renders_macro_dashboard(tmp_path):
    """HTML 생성기에서 10대 지표 대시보드와 트렌드 뱃지가 정상 렌더링되는지 검증"""
    cfg = MorningReportConfig(include_market_indices=True)
    generator = ReportHtmlGenerator(cfg)

    mock_macro_data = {
        "raw_items": {
            "sp500": {"name": "S&P 500", "symbol": "^GSPC", "price_str": "5,873.12 pt", "change_pct": 0.45, "change_str": "+0.45%", "trend": "UP", "trend_badge": "▲ 상승 추세"},
            "nasdaq100": {"name": "Nasdaq 100", "symbol": "^NDX", "price_str": "20,123.45 pt", "change_pct": 0.80, "change_str": "+0.80%", "trend": "UP", "trend_badge": "▲ 상승 추세"},
            "dow": {"name": "다우존스", "symbol": "^DJI", "price_str": "42,063.36 pt", "change_pct": -0.10, "change_str": "-0.10%", "trend": "FLAT", "trend_badge": "━ 보합세"},
            "kospi": {"name": "코스피", "symbol": "^KS11", "price_str": "2,593.37 pt", "change_pct": 0.21, "change_str": "+0.21%", "trend": "UP", "trend_badge": "▲ 상승 추세"},
            "kosdaq": {"name": "코스닥", "symbol": "^KQ11", "price_str": "748.30 pt", "change_pct": -0.15, "change_str": "-0.15%", "trend": "DOWN", "trend_badge": "▼ 하락 추세"},
            "usd_krw": {"name": "원/달러 환율", "symbol": "KRW=X", "price_str": "1,332.5원", "change_pct": -0.32, "change_str": "-0.32%", "trend": "DOWN", "trend_badge": "▼ 하락 추세"},
            "wti_oil": {"name": "WTI 국제유가", "symbol": "CL=F", "price_str": "$71.47", "change_pct": 0.50, "change_str": "+0.50%", "trend": "UP", "trend_badge": "▲ 상승 추세"},
            "us10y_yield": {"name": "미국 10년물 국채금리", "symbol": "^TNX", "price_str": "3.73%", "change_pct": -0.02, "change_str": "-0.02%p", "trend": "DOWN", "trend_badge": "▼ 하락 추세"},
        },
        "fundamentals": US_ECONOMIC_INDICATORS,
    }

    report_data = {
        "summary": {"total_eval": 50000000, "total_cost": 45000000, "total_pl": 5000000, "total_pl_pct": 11.11, "cash_balance": 1000000},
        "recommendations": {"d_day": 3, "total_recommended_amount": 1000000, "items": []},
        "positions": [],
        "news": [],
        "market_indices": {},
        "macro_indicators": mock_macro_data,
        "account_name": "테스트 계좌",
    }

    html_file = generator.generate_html(report_data, output_filename="test_macro_report.html")
    assert html_file.exists()

    content = html_file.read_text(encoding="utf-8")
    assert "글로벌 10대 지표 & 최근 트렌드" in content
    assert "S&P 500" in content
    assert "Nasdaq 100" in content
    assert "코스피" in content
    assert "원/달러 환율" in content
    assert "WTI 국제유가" in content
    assert "미국 10년물 국채금리" in content
    assert "근원 PCE" in content
    assert "비농업 신규고용" in content
    assert "실업률" in content
    assert "trend-badge-up" in content
    assert "trend-badge-down" in content


def test_daily_report_service_kakao_text_includes_macro():
    """DailyReportService의 _build_kakao_summary_text가 매크로 라인을 정상 포함하는지 검증"""
    cfg = AppConfig()
    service = DailyReportService(cfg)

    mock_macro_data = {
        "raw_items": {
            "sp500": {"price": 5873.12, "change_str": "+0.45%"},
            "nasdaq100": {"price": 20123.45, "change_str": "+0.80%"},
            "kospi": {"price": 2593.37, "change_str": "+0.21%", "trend_badge": "▲상승"},
            "usd_krw": {"price": 1332.5},
            "wti_oil": {"price": 71.47},
            "us10y_yield": {"price": 3.73},
        },
        "fundamentals": US_ECONOMIC_INDICATORS,
    }

    text = service._build_kakao_summary_text(
        account_name="ISA 계좌",
        summary={"total_eval": 10000000, "total_pl": 500000, "total_pl_pct": 5.0},
        recommendations={"d_day": 0, "total_recommended_amount": 500000, "items": []},
        news_items=[],
        report_web_url="https://test.pages.dev/report.html",
        gemini_analysis=None,
        macro_data=mock_macro_data,
    )

    assert "글로벌 10대 지표 & 최근 트렌드" in text
    assert "S&P" in text
    assert "코스피" in text
    assert "환율" in text
    assert "PCE" in text


def test_kakao_summary_with_all_registered_stocks_and_accounts():
    """전체 등록 종목 목록 및 다중 계좌 현황이 카카오톡 메시지에 완벽히 반영되는지 검증"""
    cfg = AppConfig()
    service = DailyReportService(cfg)

    positions = [
        {"name": "RISE TDF2040액티브", "shares": 100, "current_price": 12850, "pl_pct": 3.5, "current_weight": 0.55, "target_weight": 0.60},
        {"name": "TIGER 미국S&P500동일가중", "shares": 50, "current_price": 15300, "pl_pct": 1.2, "current_weight": 0.25, "target_weight": 0.25},
        {"name": "TIGER 미국나스닥TOP10", "shares": 0, "current_price": 18200, "pl_pct": 0.0, "current_weight": 0.0, "target_weight": 0.15},
    ]

    account_summaries = [
        {"name": "신한 IRP", "total_eval": 35000000, "total_pl": 1500000, "total_pl_pct": 4.5},
        {"name": "미래에셋 연금저축", "total_eval": 25000000, "total_pl": 800000, "total_pl_pct": 3.3},
    ]

    recs = {
        "d_day": 3,
        "next_buy_date": "2026-09-25",
        "total_recommended_amount": 1200000,
        "items": [
            {"name": "RISE TDF2040액티브", "recommended_shares": 5, "recommended_amount": 64250},
            {"name": "TIGER 미국나스닥TOP10", "recommended_shares": 10, "recommended_amount": 182000},
        ],
    }

    text = service._build_kakao_summary_text(
        account_name="전체 통합 포트폴리오 (2개 계좌)",
        summary={"total_eval": 60000000, "total_pl": 2300000, "total_pl_pct": 3.98},
        recommendations=recs,
        news_items=[],
        report_web_url="https://test.pages.dev/report.html",
        positions=positions,
        account_summaries=account_summaries,
    )

    # 1. 전체 계좌 및 계좌별 요약 포함
    assert "전체 통합 포트폴리오 (2개 계좌)" in text
    assert "신한 IRP" in text
    assert "미래에셋 연금저축" in text

    # 2. 전체 등록 종목 현황 포함 (보유 + 미보유 등록 종목)
    assert "📋 전체 등록 종목 현황 (3개):" in text
    assert "RISE TDF2040액티브" in text
    assert "TIGER 미국S&P500동일가중" in text
    assert "TIGER 미국나스닥TOP10" in text
    assert "미보유" in text

    # 3. 전체 추천 종목 포함
    assert "🎯 이번 주기 추천 매수 (2종목):" in text
    assert "+5주" in text
    assert "+10주" in text
