"""
tests/test_gemini_service.py
Google Gemini AI 매크로 투자 가이드 서비스 단위 테스트.
- 초기화 및 기본 모델(gemini-3.8-flash) 검증
- 프롬프트 구성 및 JSON 응답 파싱 검증
- API 모킹 및 자동 하위 모델 폴백(Auto-Fallback) 검증
- 장애 시 무중단 안전 대체의 Graceful Fallback 검증
"""

import json
import urllib.error
from unittest.mock import patch, MagicMock
import pytest

from core.config import AppConfig, MorningReportConfig
from services.gemini_service import GeminiService, FALLBACK_MODELS


def test_gemini_service_initialization():
    """기본 초기화 시 gemini-3.8-flash 모델과 설정 검증"""
    cfg = AppConfig()
    cfg.morning_report.gemini_model = "gemini-3.8-flash"
    cfg.morning_report.gemini_api_key = ""

    service = GeminiService(config=cfg)
    assert service.model == "gemini-3.8-flash"
    assert not service.is_configured()

    service_with_key = GeminiService(config=cfg, api_key="AIzaSyTestKey12345")
    assert service_with_key.is_configured()


def test_prompt_building():
    """프롬프트에 계좌 요약, 환율, 추천 종목이 정상 반영되는지 검증"""
    service = GeminiService(api_key="AIzaSyDummyKey")
    context = {
        "account_name": "신한 IRP 연금",
        "summary": {
            "total_eval": 55000000,
            "total_pl": 2500000,
            "total_pl_pct": 4.5,
            "cash_balance": 3000000,
        },
        "recommendations": {
            "d_day": 3,
            "next_buy_date": "2026-09-25",
            "items": [
                {
                    "name": "RISE TDF2040액티브",
                    "recommended_shares": 10,
                    "reason": "목표 비중 대비 5% 부족",
                }
            ],
        },
        "positions": [
            {
                "name": "RISE TDF2040액티브",
                "current_weight": 0.55,
                "target_weight": 0.60,
                "pl_pct": 3.2,
            }
        ],
        "news": [{"title": "미국 금리 인하 기대감 고조", "media": "한국경제"}],
        "market_indices": {"KODEX 200": {"price": "35,000원", "change_pct": 0.5}},
    }

    prompt = service._build_prompt(context, usd_krw="1,385.0원")
    assert "신한 IRP 연금" in prompt
    assert "1,385.0원" in prompt
    assert "RISE TDF2040액티브" in prompt
    assert "미국 금리 인하 기대감 고조" in prompt


def test_parse_json_response():
    """마크다운 코드블록 및 일반 JSON 문자열 안전 파싱 검증"""
    service = GeminiService(api_key="AIzaSyDummyKey")

    # 1. ```json ... ``` 형식
    mock_md = """```json
    {
        "one_line_summary": "📈 환율 안정세 속 TDF 분할 매수가 유리합니다.",
        "macro_analysis": "미국 증시 기술주 반등으로 글로벌 위험자산 선호가 회복되었습니다.",
        "strategy_advice": "D-3일 정기 매수일을 앞두고 목표 비중을 회복하는 분할 매수를 권장합니다."
    }
    ```"""
    res1 = service._parse_json_response(mock_md)
    assert "📈 환율 안정세" in res1["one_line_summary"]
    assert "기술주 반등" in res1["macro_analysis"]

    # 2. '''json ... ''' 형식 및 내부 따옴표 이스케이프 누락 (사용자 제보 버그 패턴)
    user_bug_md = """'''json
    {
        "one_line"summary": "📈 나스닥 강세와 유가 하락 속, 분할 매수 적기입니다.",
        "macro_analysis": "미국 증시는 "매그니피센트 7" 실적 호조로 상승세를 보였으며, 국제 유가(WTI) 하락으로 물가 부담이 경감되었습니다.",
        "strategy_advice": "현재 목표 비중 대비 부족한 ETF를 1순위로 분할 매수하세요."
    }
    '''"""
    res_bug = service._parse_json_response(user_bug_md)
    assert "📈 나스닥 강세" in res_bug["one_line_summary"]
    assert "매그니피센트 7" in res_bug["macro_analysis"]
    assert "'''json" not in res_bug["macro_analysis"]
    assert "one_line" not in res_bug["macro_analysis"]

    # 3. 마감 중괄호 누락(Truncated JSON) 복구 검증
    truncated_md = """```json
    {
        "one_line_summary": "📈 유가 안정세 지속",
        "macro_analysis": "WTI 유가 하락으로 인플레 우려가 완화되었습니다.",
        "strategy_advice": "분할 매수 계획을 유지하세요.
    """
    res_trunc = service._parse_json_response(truncated_md)
    assert "WTI 유가 하락" in res_trunc["macro_analysis"]
    assert "```json" not in res_trunc["macro_analysis"]

    # 4. 후행 쉼표(Trailing Comma) 허용 검증
    trailing_comma_md = """{
        "one_line_summary": "📊 시장 안정세",
        "macro_analysis": "글로벌 증시가 안정권에 진입했습니다.",
        "strategy_advice": "정기 매수를 권장합니다.",
    }"""
    res_tc = service._parse_json_response(trailing_comma_md)
    assert "글로벌 증시" in res_tc["macro_analysis"]

    # 5. 비정형 텍스트 및 JSON 파싱 최종 실패 시 마크다운/JSON 키워드 제거 검증
    raw_text = "이것은 일반 텍스트 응답입니다."
    res2 = service._parse_json_response(raw_text)
    assert "이것은 일반 텍스트 응답입니다." in res2["macro_analysis"]
    assert "{" not in res2["macro_analysis"]


def test_api_call_success_mock():
    """Gemini API 정상 응답 시 파싱 및 반환 구조 검증"""
    service = GeminiService(api_key="AIzaSyValidKey", model="gemini-3.8-flash")

    mock_gemini_payload = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": json.dumps({
                                "one_line_summary": "✨ 금일 환율 안정 및 S&P500 호조로 긍정적 흐름 예상됩니다.",
                                "macro_analysis": "전일 뉴욕 3대 지수가 모두 상승하며 위험자산 투자 심리가 개선되었습니다.",
                                "strategy_advice": "원칙대로 계획된 TDF 적립식 매수를 추천드립니다.",
                            })
                        }
                    ]
                }
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_gemini_payload).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = service.generate_macro_investment_guide({"account_name": "테스트 계좌"})
        assert res["success"] is True
        assert res["model_used"] == "gemini-3.8-flash"
        assert "✨ 금일 환율 안정" in res["one_line_summary"]
        assert "위험자산 투자 심리" in res["macro_analysis"]


def test_auto_fallback_on_404_model_not_found():
    """3.8 모델이 404일 때 하위 모델(3.7, 2.5 등)로 자동 폴백하여 성공하는지 검증"""
    service = GeminiService(api_key="AIzaSyValidKey", model="gemini-3.8-flash")

    call_count = 0

    def mock_urlopen(req, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        url = req.full_url
        if "gemini-3.8-flash" in url:
            # 3.8 모델은 404 에러 발생 모킹
            fp = MagicMock()
            fp.read.return_value = b'{"error": {"code": 404, "message": "models/gemini-3.8-flash is not found"}}'
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, fp)
        else:
            # 폴백 모델은 정상 응답
            resp = MagicMock()
            mock_payload = {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps({
                                        "one_line_summary": "💡 폴백 모델(gemini-3.7-flash)에서 정상 응답",
                                        "macro_analysis": "시황 분석 성공",
                                        "strategy_advice": "전략 조언 성공",
                                    })
                                }
                            ]
                        }
                    }
                ]
            }
            resp.read.return_value = json.dumps(mock_payload).encode("utf-8")
            resp.__enter__.return_value = resp
            return resp

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        res = service.generate_macro_investment_guide({"account_name": "폴백 테스트"})
        assert res["success"] is True
        assert res["model_used"] == "gemini-3.6-flash"
        assert call_count >= 2


def test_auto_fallback_on_503_high_demand():
    """3.8 모델이 503(일시적 과부하)일 때 gemini-3.6-flash로 즉시 폴백하여 성공하는지 검증"""
    service = GeminiService(api_key="AIzaSyValidKey", model="gemini-3.8-flash")
    call_count = 0

    def mock_urlopen(req, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        url = req.full_url
        if "gemini-3.8-flash" in url:
            fp = MagicMock()
            fp.read.return_value = b'{"error": {"code": 503, "message": "This model is currently experiencing high demand."}}'
            raise urllib.error.HTTPError(url, 503, "Service Unavailable", {}, fp)
        else:
            resp = MagicMock()
            mock_payload = {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps({
                                        "one_line_summary": "💡 gemini-3.6-flash 정상 응답",
                                        "macro_analysis": "시황 분석 성공",
                                        "strategy_advice": "전략 조언 성공",
                                    })
                                }
                            ]
                        }
                    }
                ]
            }
            resp.read.return_value = json.dumps(mock_payload).encode("utf-8")
            resp.__enter__.return_value = resp
            return resp

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        res = service.generate_macro_investment_guide({"account_name": "503 폴백 테스트"})
        assert res["success"] is True
        assert res["model_used"] == "gemini-3.6-flash"
        assert call_count >= 2


def test_graceful_fallback_when_api_unconfigured():
    """API 키가 비어있을 때 크래시 없이 안전하게 실패 객체 반환 검증"""
    service = GeminiService(api_key="")
    res = service.generate_macro_investment_guide({})
    assert res["success"] is False
    assert res["one_line_summary"] == ""
    assert "stance_badge" in res


def test_investment_stance_profiles_and_prompt_injection():
    """5단계 투자 성향 설정 및 프롬프트 주입 검증"""
    from services.gemini_service import INVESTMENT_STANCE_PROFILES

    # 1. 5개 프로필이 모두 정의되어 있는지 검증
    expected_stances = ["very_conservative", "conservative", "balanced", "aggressive", "very_aggressive"]
    for s in expected_stances:
        assert s in INVESTMENT_STANCE_PROFILES
        assert "badge" in INVESTMENT_STANCE_PROFILES[s]
        assert "prompt_instruction" in INVESTMENT_STANCE_PROFILES[s]
        assert "fallback_advice" in INVESTMENT_STANCE_PROFILES[s]

    # 2. 공격적 성향 프롬프트 주입 검증
    service_agg = GeminiService(api_key="test", investment_stance="aggressive")
    assert service_agg.investment_stance == "aggressive"
    prompt_agg = service_agg._build_prompt({})
    assert "공격적" in prompt_agg
    assert "기회" in prompt_agg

    # 3. 매우 보수적 성향 프롬프트 주입 검증
    service_cons = GeminiService(api_key="test", investment_stance="very_conservative")
    assert service_cons.investment_stance == "very_conservative"
    prompt_cons = service_cons._build_prompt({})
    assert "매우 보수적" in prompt_cons
    assert "원금 보존" in prompt_cons

    # 4. 잘못된 성향 전달 시 기본값(balanced) 자동 보정
    service_invalid = GeminiService(api_key="test", investment_stance="invalid_xyz")
    assert service_invalid.investment_stance == "balanced"

