"""
services/gemini_service.py
Google Gemini 생성형 AI (기본 모델: gemini-3.8-flash) 연동 매크로 투자 가이드 서비스.
- 환율(USD/KRW), 글로벌 시황, 수집 뉴스, 포트폴리오 현황을 결합한 심층 AI 브리핑 생성
- 카카오톡 모닝 브리핑용 'AI 한 줄 시황' 및 모바일 웹 리포트용 '글로벌 매크로 분석 & 투자 조언' 제공
- 모델 장애 시 자동 하위 모델(3.8 -> 3.7 -> 2.5 -> 2.0) 폴백(Auto-Fallback) 지원
- API Key 미설정 또는 장애 시에도 무중단 안전 대체의 Graceful Degradation 보장
"""

from __future__ import annotations
import os
import re
import ssl
import json
import logging
import urllib.request
import urllib.parse
from typing import Dict, Any, Optional, Tuple, List

from core.config import AppConfig, load_config

logger = logging.getLogger("RetirementPortfolio.GeminiService")

# 자동 폴백 모델 우선순위 리스트 (Google 권장 Flash 라인업)
FALLBACK_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.7-flash",
]

INVESTMENT_STANCE_PROFILES: Dict[str, Dict[str, str]] = {
    "very_conservative": {
        "label": "매우 보수적",
        "badge": "🛡️ 매우 보수적",
        "short_desc": "원금 보존 최우선 / 방어적 현금 확보",
        "description": "원금 보존 최우선. 불확실성 감지 시 현금 확보 및 분할매수 속도 조절을 권고하며, TDF·배당 중심의 방어적 운용을 조언합니다.",
        "prompt_instruction": (
            "[투자자 맞춤 투자 성향: '매우 보수적 (원금 보존 최우선)']\n"
            "- 투자자는 원금 보존과 하방 리스크 방어를 최우선 가치로 생각합니다.\n"
            "- 조언 지침:\n"
            "  1) 매크로 지표에 불안 요소(금리 급등, 환율 급등, 유가 불안 등)가 있다면 섣부른 매수보다는 '현금 비중 확보 및 관망'을 권고하세요.\n"
            "  2) 고변동성/레버리지/성장 기술주보다는 TDF, 채권, 배당 등 안정적 자산 중심의 신중한 접근을 권장하세요.\n"
            "  3) '원금의 안정성을 지키며 확실한 기회를 기다리는 것이 현명합니다'와 같이 방어적이고 신중한 어조로 조언하세요."
        ),
        "fallback_advice": "시장 변동성 장세에서는 무리한 매수보다 현금 비중 확보와 TDF 등 안정적 자산 중심의 방어적 운용이 유리합니다.",
    },
    "conservative": {
        "label": "보수적",
        "badge": "🛡️ 보수적",
        "short_desc": "안정 추구 / 단계적 분할 매수",
        "description": "안정 추구. 추격 매수를 지양하고 바닥 확인 후 차분하게 분할 매수하도록 권고하며, 목표 비중 내 신중한 자산배분을 유지합니다.",
        "prompt_instruction": (
            "[투자자 맞춤 투자 성향: '보수적 (안정 추구)']\n"
            "- 투자자는 안정적인 성장을 선호하며 하방 리스크 관리를 중시합니다.\n"
            "- 조언 지침:\n"
            "  1) 시장 상승 시 추격 매수를 경계하고, 하락 시에도 지지력을 확인하며 차분히 나누어 매수하도록 조언하세요.\n"
            "  2) 목표 비중을 무리하게 채우기보다 정해진 주기에 맞춘 차분한 단계적 분할 매수를 권고하세요.\n"
            "  3) '급등락에 흔들리지 않고 안전 마진을 확보하는 분할 매수가 유리합니다'와 같이 신중한 어조로 조언하세요."
        ),
        "fallback_advice": "시장 흐름을 차분히 관망하며 목표 비중에 맞춘 신중하고 단계적인 분할 매수를 유지하시기 바랍니다.",
    },
    "balanced": {
        "label": "중립적 / 균형",
        "badge": "⚖️ 중립/균형",
        "short_desc": "장기 자산배분 / 원칙 기반 판단",
        "description": (
            "장기 자산배분 원칙을 유지하면서 시장 환경, "
            "목표 비중 괴리와 계좌별 매수 가능 범위를 함께 검토합니다. "
            "매수 가능 예산이 존재하더라도 자동으로 집행하지 않고 "
            "매수·일부 매수·대기 중 합리적인 행동을 판단합니다."
        ),
        "prompt_instruction": (
            "[투자자 맞춤 투자 성향: '중립적 / 균형 (장기 자산배분)']\n"
            "- 투자자는 감정적인 단기 매매를 피하고 장기 자산배분 원칙을 중시합니다.\n"
            "- 조언 지침:\n"
            "  1) 매크로 지표와 포트폴리오 상태를 객관적으로 분석하세요.\n"
            "  2) 목표 비중 괴리와 시스템이 계산한 매수 가능 범위를 참고하되, "
            "그 자체를 매수 명령으로 해석하지 마세요.\n"
            "  3) 시장 환경과 사용자 투자 원칙을 함께 검토하여 "
            "매수, 일부 분할매수, 대기 또는 기존 계획 유지 중 적절한 행동을 판단하세요.\n"
            "  4) 매수 근거가 충분하지 않다면 매수 가능 예산이 남아 있어도 "
            "대기를 정상적인 선택으로 제시하세요."
        ),
        "fallback_advice": (
            "목표 비중과 매수 가능 범위를 참고하되 자동으로 집행하지 말고, "
            "시장 상황을 확인하면서 장기 자산배분 계획을 유지하시기 바랍니다."
        ),
    },
    "aggressive": {
        "label": "공격적",
        "badge": "🚀 공격적",
        "short_desc": "기회 포착 / 성장 및 저가매수 적극",
        "description": "기회 포착. 단기 조정이나 시장 하락을 '저가 매수의 호기'로 적극 해석하여 성장주 및 핵심 ETF의 적극적 분할 매수를 독려합니다.",
        "prompt_instruction": (
            "[투자자 맞춤 투자 성향: '공격적 (기회 포착 및 성장 추구)']\n"
            "- 투자자는 장기 고수익을 목표로 단기 변동성을 적극적으로 감내합니다.\n"
            "- 조언 지침:\n"
            "  1) 시장 조정이나 하락 지표가 보일 때 공포에 위축되지 말고 '우량 ETF를 할인된 가격에 담는 절호의 기회'로 적극 해석하세요.\n"
            "  2) 목표 비중이 부족한 성장형 ETF(미국테크, S&P500 등)를 과감하게 편입하도록 용기를 북돋우세요.\n"
            "  3) '시장의 일시적 흔들림은 장기 투자자에게 최고의 매수 기회입니다'와 같이 진취적이고 확신에 찬 어조로 조언하세요."
        ),
        "fallback_advice": "단기 조정은 우량 ETF를 저렴하게 매수할 호기입니다. 성장형 ETF를 중심으로 적극적인 분할 매수를 추천합니다.",
    },
    "very_aggressive": {
        "label": "매우 공격적",
        "badge": "🔥 매우 공격적",
        "short_desc": "수익 극대화 / 과감한 Buy the Dip",
        "description": "수익 극대화 (Buy the Dip). 하락장 공포 속에서 공격적인 추가 매수를 권장하여 평단가를 대폭 낮추고 반등 모멘텀을 극대화합니다.",
        "prompt_instruction": (
            "[투자자 맞춤 투자 성향: '매우 공격적 (수익 극대화 및 과감한 Buy the Dip)']\n"
            "- 투자자는 극대화된 수익률을 위해 가장 공격적인 투자 자세를 지향합니다.\n"
            "- 조언 지침:\n"
            "  1) 강한 하락장이나 드로다운 발생 시 '탐욕을 부릴 최적의 타이밍'으로 판단하고, 가용 자금을 동원한 과감한 저가 추가 매수(Buy the Dip)를 강력히 권장하세요.\n"
            "  2) 평단가를 대폭 낮추고 향후 도래할 반등장에서 최대의 수익을 수확할 수 있도록 공격적인 매수 포지션을 독려하세요.\n"
            "  3) '남들이 두려워할 때 담대하게 비중을 확대하여 반등의 주인공이 되세요'와 같이 열정적이고 공격적인 어조로 조언하세요."
        ),
        "fallback_advice": "공포 장세야말로 극대화된 수익을 위한 매수 적기입니다. 과감한 저가 분할 매수로 평단가를 낮추시길 권장합니다.",
    },
}

STANCE_KEYS: List[str] = [
    "very_conservative",
    "conservative",
    "balanced",
    "aggressive",
    "very_aggressive",
]


class GeminiService:
    """Google Gemini AI API 연동 서비스"""

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        investment_stance: Optional[str] = None,
    ):
        self.config = config or load_config()
        # API Key 우선순위: 명시적 인자 -> config -> 환경변수
        m_cfg = getattr(self.config, "morning_report", None)
        cfg_key = getattr(m_cfg, "gemini_api_key", "") if m_cfg else ""
        cfg_model = getattr(m_cfg, "gemini_model", "gemini-3.8-flash") if m_cfg else "gemini-3.8-flash"
        cfg_stance = getattr(m_cfg, "ai_investment_stance", "balanced") if m_cfg else "balanced"

        if api_key is not None:
            self.api_key = api_key.strip()
        elif config is not None:
            self.api_key = cfg_key.strip()
        else:
            self.api_key = (cfg_key or os.getenv("GEMINI_API_KEY", "")).strip()

        if model is not None:
            self.model = model.strip()
        else:
            self.model = (cfg_model or os.getenv("GEMINI_MODEL", "gemini-3.8-flash")).strip()
        if not self.model:
            self.model = "gemini-3.8-flash"

        self.investment_stance = (investment_stance or cfg_stance or os.getenv("AI_INVESTMENT_STANCE", "balanced")).strip().lower()
        if self.investment_stance not in INVESTMENT_STANCE_PROFILES:
            self.investment_stance = "balanced"

        self.ssl_context = ssl._create_unverified_context()

    def is_configured(self) -> bool:
        """Gemini API 키가 정상적으로 설정되어 있는지 확인"""
        return bool(self.api_key and len(self.api_key) > 5)

    def fetch_macro_context(self) -> Dict[str, Any]:
        """실시간 거시경제(USD/KRW 환율 등) 보조 지표 수집"""
        context = {
            "usd_krw": "조회 불가",
        }
        try:
            url = "https://open.er-api.com/v6/latest/USD"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, context=self.ssl_context, timeout=4) as res:
                data = json.loads(res.read().decode("utf-8"))
                krw = data.get("rates", {}).get("KRW")
                if krw:
                    context["usd_krw"] = f"{krw:,.1f}원"
        except Exception as e:
            logger.debug(f"USD/KRW 환율 수집 생략: {e}")

        return context

    def test_connection(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Gemini API 연결 및 모델 동작 여부를 즉시 테스트합니다.
        반환값: (성공 여부, 응답 메시지)
        """
        test_key = (api_key or self.api_key).strip()
        test_model = (model or self.model).strip() or "gemini-3.8-flash"

        if not test_key:
            return False, "Gemini API 키가 입력되지 않았습니다. Google AI Studio에서 키를 발급받으세요."

        test_prompt = "안녕하세요! 퇴직연금 포트폴리오 매니저 Gemini 연동 테스트입니다. 한 줄로 활기찬 아침 응원 인사를 해주세요."
        try:
            success, result_model, response_text = self._call_gemini_api(
                prompt=test_prompt,
                model=test_model,
                api_key=test_key,
                allow_fallback=True,
            )
            if success:
                return True, f"[{result_model}] 연결 성공!\nAI 응답: {response_text.strip()}"
            else:
                return False, f"연결 실패: {response_text}"
        except Exception as e:
            return False, f"연결 테스트 중 예외 발생: {str(e)}"

    def generate_macro_investment_guide(
        self,
        report_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        포트폴리오 현황과 시장 매크로 데이터를 바탕으로 Gemini AI 투자 가이드를 생성합니다.
        """
        stance_info = INVESTMENT_STANCE_PROFILES.get(self.investment_stance, INVESTMENT_STANCE_PROFILES["balanced"])
        if not self.is_configured():
            logger.info("Gemini API 키가 설정되지 않아 AI 매크로 가이드를 생성하지 않습니다.")
            return {
                "success": False,
                "error": "Gemini API 키 미설정",
                "model_used": self.model,
                "investment_stance": self.investment_stance,
                "stance_badge": stance_info["badge"],
                "stance_label": stance_info["label"],
                "one_line_summary": "",
                "macro_analysis": "",
                "strategy_advice": "",
            }

        # 1. 10대 매크로 지표 및 트렌드 요약, 환율 확인
        macro_summary = report_context.get("macro_summary", "")
        macro_ind = report_context.get("macro_indicators", {})
        usd_krw = ""
        if macro_ind:
            usd_krw = macro_ind.get("raw_items", {}).get("usd_krw", {}).get("price_str", "")

        if not macro_summary:
            try:
                from services.macro_indicator_service import MacroIndicatorService
                macro_srv = MacroIndicatorService()
                macro_data = macro_srv.fetch_all_macro_data()
                macro_summary = macro_srv.build_summary_for_gemini(macro_data)
                if not usd_krw:
                    usd_krw = macro_data.get("raw_items", {}).get("usd_krw", {}).get("price_str", "")
            except Exception as e:
                logger.debug(f"매크로 지표 자동 수집 생략: {e}")
                macro_summary = ""

        if not usd_krw:
            try:
                usd_krw = self.fetch_macro_context().get("usd_krw", "")
            except Exception:
                usd_krw = ""

        # 2. 프롬프트 구성
        prompt = self._build_prompt(
            report_context,
            macro_summary,
            usd_krw=usd_krw,
        )

        # 3. Gemini API 호출 (자동 폴백 포함 및 구조화 JSON 모드 활성화)
        success, used_model, raw_response = self._call_gemini_api(
            prompt=prompt,
            model=self.model,
            api_key=self.api_key,
            allow_fallback=True,
            json_mode=True,
        )

        if not success:
            logger.warning(f"Gemini API 호출 실패: {raw_response}")
            return {
                "success": False,
                "error": raw_response,
                "model_used": used_model,
                "investment_stance": self.investment_stance,
                "stance_badge": stance_info["badge"],
                "stance_label": stance_info["label"],
                "one_line_summary": "",
                "macro_analysis": "",
                "strategy_advice": stance_info.get("fallback_advice", ""),
                "usd_krw": usd_krw,
            }

        # 4. JSON 파싱
        parsed = self._parse_json_response(raw_response)

        action = str(
            parsed.get(
                "action",
                "HOLD",
            )
            or "HOLD"
        ).strip().upper()

        action_labels = {
            "BUY": "매수",
            "PARTIAL": "일부 매수",
            "WAIT": "대기",
            "HOLD": "기존 계획 유지",
        }

        if action not in action_labels:
            action = "HOLD"

        return {
            "success": True,
            "model_used": used_model,
            "investment_stance": self.investment_stance,
            "stance_badge": stance_info["badge"],
            "stance_label": stance_info["label"],
            "action": action,
            "action_label": action_labels[action],
            "one_line_summary": parsed.get("one_line_summary", "").strip(),
            "macro_analysis": parsed.get("macro_analysis", "").strip(),
            "strategy_advice": parsed.get("strategy_advice", "").strip(),
            "usd_krw": usd_krw,
            "raw_text": raw_response,
        }

    def _call_gemini_api(
        self,
        prompt: str,
        model: str,
        api_key: str,
        allow_fallback: bool = True,
        json_mode: bool = False,
    ) -> Tuple[bool, str, str]:
        """
        Gemini REST API 호출을 실행하며, 404/모델 미지원 시 하위 모델로 자동 폴백합니다.
        반환값: (성공 여부, 실제 사용된 모델명, 응답 텍스트 또는 에러 메시지)
        """
        models_to_try = [model]
        if allow_fallback:
            for fb in FALLBACK_MODELS:
                if fb not in models_to_try:
                    models_to_try.append(fb)

        last_error = ""
        for m in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={api_key}"
            gen_config: Dict[str, Any] = {
                "temperature": 0.4,
                "maxOutputTokens": 3000,
            }
            if json_mode:
                gen_config["responseMimeType"] = "application/json"

            payload = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": prompt}],
                    }
                ],
                "generationConfig": gen_config,
            }
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=req_data,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "PortfolioManager/1.0",
                },
                method="POST",
            )

            try:
                with urllib.request.urlopen(req, context=self.ssl_context, timeout=20) as resp:
                    resp_bytes = resp.read()
                    data = json.loads(resp_bytes.decode("utf-8"))
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            text = parts[0].get("text", "")
                            return True, m, text
                    return False, m, "응답 본문에 유효한 텍스트가 없습니다."

            except urllib.error.HTTPError as e:
                err_body = ""
                try:
                    err_body = e.read().decode("utf-8", "replace")
                except Exception:
                    pass
                last_error = f"HTTP {e.code}: {err_body or e.reason}"
                logger.warning(f"Gemini 모델 [{m}] 호출 실패 ({e.code}): {err_body}")

                # 키 자체 오류(401, 403)는 어떤 모델을 써도 실패하므로 즉시 중단
                if e.code in (401, 403):
                    return False, m, last_error

                # 400 에러 중 responseMimeType 미지원인 경우 일반 텍스트 모드로 1회 재시도
                if e.code == 400 and json_mode and "responseMimeType" in err_body:
                    try:
                        fallback_payload = dict(payload)
                        fallback_payload["generationConfig"] = {"temperature": 0.4, "maxOutputTokens": 3000}
                        req_fb = urllib.request.Request(
                            url,
                            data=json.dumps(fallback_payload).encode("utf-8"),
                            headers={"Content-Type": "application/json", "User-Agent": "PortfolioManager/1.0"},
                            method="POST",
                        )
                        with urllib.request.urlopen(req_fb, context=self.ssl_context, timeout=20) as resp:
                            data = json.loads(resp.read().decode("utf-8"))
                            candidates = data.get("candidates", [])
                            if candidates:
                                parts = candidates[0].get("content", {}).get("parts", [])
                                if parts:
                                    return True, m, parts[0].get("text", "")
                    except Exception:
                        pass

                # 404(모델 미지원), 400(잘못된 모델명), 503/502/500(서버 과부하), 429(할당량 초과)는 다음 폴백 모델로 시도
                if allow_fallback and e.code in (404, 400, 429, 500, 502, 503):
                    continue

            except Exception as e:
                last_error = str(e)
                logger.warning(f"Gemini 모델 [{m}] 호출 중 네트워크 오류: {e}")
                if allow_fallback:
                    continue

        return False, models_to_try[0], last_error

    def _build_prompt(
        self,
        ctx: Dict[str, Any],
        macro_summary: str = "",
        usd_krw: str = "",
        **kwargs,
    ) -> str:
        """
        사용자 투자 원칙과 계좌별 실제 운용 규칙을 반영하여
        Gemini 투자 가이드 프롬프트를 생성합니다.
        """

        summary = ctx.get(
            "summary",
            {},
        )

        recommendations = ctx.get(
            "recommendations",
            {},
        )

        positions = ctx.get(
            "positions",
            [],
        )

        news_items = ctx.get(
            "news",
            [],
        )

        account_name = ctx.get(
            "account_name",
            "포트폴리오",
        )

        account_groups = ctx.get(
            "account_groups",
            [],
        ) or []

        account_recommendations = ctx.get(
            "account_recommendations",
            [],
        ) or []

        investment_profile = (
            ctx.get("investment_profile")
            or {}
        )

        # -------------------------------------------------
        # 사용자 전체 투자 성향
        # -------------------------------------------------

        user_risk_profile = str(
            investment_profile.get(
                "risk_profile",
                self.investment_stance,
            )
            or self.investment_stance
        ).strip().lower()

        if (
            user_risk_profile
            not in INVESTMENT_STANCE_PROFILES
        ):
            user_risk_profile = (
                self.investment_stance
            )

        investment_horizon_years = (
            investment_profile.get(
                "investment_horizon_years"
            )
        )

        ai_advice_style = str(
            investment_profile.get(
                "ai_advice_style",
                user_risk_profile,
            )
            or user_risk_profile
        ).strip().lower()

        investment_preference_text = str(
            investment_profile.get(
                "investment_preference_text",
                "",
            )
            or ""
        ).strip()

        effective_stance = (
            ai_advice_style
            if ai_advice_style
            in INVESTMENT_STANCE_PROFILES
            else user_risk_profile
        )

        stance_info = (
            INVESTMENT_STANCE_PROFILES.get(
                effective_stance,
                INVESTMENT_STANCE_PROFILES[
                    "balanced"
                ],
            )
        )

        stance_instruction = (
            stance_info[
                "prompt_instruction"
            ]
        )

        horizon_text = (
            f"{investment_horizon_years}년"
            if investment_horizon_years
            is not None
            else "미설정"
        )

        preference_text = (
            investment_preference_text
            if investment_preference_text
            else "별도의 자유 입력 투자 원칙 없음"
        )

        # -------------------------------------------------
        # 전체 포트폴리오
        # -------------------------------------------------

        total_eval = float(
            summary.get(
                "total_eval",
                0,
            )
            or 0
        )

        total_pl = float(
            summary.get(
                "total_pl",
                0,
            )
            or 0
        )

        total_pl_pct = float(
            summary.get(
                "total_pl_pct",
                0,
            )
            or 0
        )

        cash_balance = float(
            summary.get(
                "cash_balance",
                0,
            )
            or 0
        )

        # -------------------------------------------------
        # 계좌별 추천 정보를 빠르게 찾기 위한 맵
        # -------------------------------------------------

        recommendation_map = {}

        for item in account_recommendations:

            account_id = item.get(
                "account_id"
            )

            if account_id is not None:
                recommendation_map[
                    account_id
                ] = item

        # -------------------------------------------------
        # 계좌별 실제 운용 규칙
        # -------------------------------------------------

        account_rule_lines = []

        for account in account_groups:

            acc_id = account.get(
                "account_id"
            )

            acc_name = account.get(
                "account_name",
                "계좌",
            )

            broker = account.get(
                "broker",
                "",
            )

            currency = str(
                account.get(
                    "currency",
                    "KRW",
                )
                or "KRW"
            ).upper()

            account_type = str(
                account.get(
                    "account_type",
                    "brokerage",
                )
                or "brokerage"
            )

            market_scope = str(
                account.get(
                    "market_scope",
                    "KR",
                )
                or "KR"
            ).upper()

            strategy_type = str(
                account.get(
                    "strategy_type",
                    "allocation",
                )
                or "allocation"
            )

            initial_capital = float(
                account.get(
                    "initial_capital",
                    0,
                )
                or 0
            )

            base_monthly = float(
                account.get(
                    "base_monthly",
                    0,
                )
                or 0
            )

            max_additional = float(
                account.get(
                    "max_additional_monthly",
                    0,
                )
                or 0
            )

            contribution_type = str(
                account.get(
                    "contribution_type",
                    "none",
                )
                or "none"
            )

            contribution_amount = float(
                account.get(
                    "contribution_amount",
                    0,
                )
                or 0
            )

            contribution_month = (
                account.get(
                    "contribution_month"
                )
            )

            buy_cycle_type = str(
                account.get(
                    "buy_cycle_type",
                    "monthly",
                )
                or "monthly"
            )

            buy_cycle_detail = str(
                account.get(
                    "buy_cycle_detail",
                    "",
                )
                or ""
            )

            acc_eval = float(
                account.get(
                    "total_eval",
                    0,
                )
                or 0
            )

            acc_cash = float(
                account.get(
                    "cash_balance",
                    0,
                )
                or 0
            )

            currency_symbol = (
                "$"
                if currency == "USD"
                else "₩"
            )

            if contribution_type == "yearly":

                if contribution_amount > 0:
                    contribution_desc = (
                        f"연 1회 "
                        f"{currency_symbol}"
                        f"{contribution_amount:,.0f}"
                    )
                else:
                    contribution_desc = (
                        "연 1회, 금액 미정"
                    )

                if contribution_month:
                    contribution_desc += (
                        f", {contribution_month}월"
                    )

            elif contribution_type == "monthly":

                contribution_desc = (
                    f"매월 "
                    f"{currency_symbol}"
                    f"{contribution_amount:,.0f}"
                )

            elif contribution_type == "irregular":

                contribution_desc = (
                    "비정기 외부자금 납입"
                )

            else:

                contribution_desc = (
                    "정기 외부자금 납입 없음"
                )

            if buy_cycle_type == "monthly":

                buy_cycle_desc = (
                    f"매월 {buy_cycle_detail}일"
                )

            else:

                buy_cycle_desc = (
                    f"{buy_cycle_type}"
                )

                if buy_cycle_detail:
                    buy_cycle_desc += (
                        f" ({buy_cycle_detail})"
                    )

            rec = recommendation_map.get(
                acc_id,
                {},
            )

            rec_items = rec.get(
                "items",
                [],
            ) or []

            rec_items = [
                item
                for item in rec_items
                if float(
                    item.get(
                        "available_buy_budget",
                        0,
                    )
                    or 0
                ) > 0
                or int(
                    item.get(
                        "available_buy_shares",
                        0,
                    )
                    or 0
                ) > 0
            ]
            
            if rec_items:

                rec_desc_parts = []

                for item in rec_items[:3]:

                    item_name = item.get(
                        "name",
                        item.get(
                            "ticker",
                            "",
                        ),
                    )

                    available_budget = float(
                        item.get(
                            "available_buy_budget",
                            0,
                        )
                        or 0
                    )

                    available_shares = int(
                        item.get(
                            "available_buy_shares",
                            0,
                        )
                        or 0
                    )

                    executable_amount = float(
                        item.get(
                            "executable_buy_amount",
                            0,
                        )
                        or 0
                    )

                    rec_desc_parts.append(
                        (
                            f"{item_name}: "
                            f"사용 가능 예산 "
                            f"{currency_symbol}"
                            f"{available_budget:,.0f}, "
                            f"예산상 최대 "
                            f"{available_shares}주, "
                            f"해당 수량 실제 금액 "
                            f"{currency_symbol}"
                            f"{executable_amount:,.0f}"
                        )
                    )

                rec_desc = "; ".join(
                    rec_desc_parts
                )

            elif rec.get(
                "already_invested_this_month",
                False,
            ):

                rec_desc = (
                    "현재 규칙상 이번 주기 "
                    "추가 사용 가능 매수예산 없음"
                )

            else:

                rec_desc = (
                    "현재 규칙상 사용 가능 "
                    "매수예산 없음"
                )
                
            account_rule_lines.extend(
                [
                    f"[계좌: {acc_name}]",
                    (
                        f"- 증권사: "
                        f"{broker or '미설정'}"
                    ),
                    (
                        f"- 계좌 유형: "
                        f"{account_type}"
                    ),
                    (
                        f"- 기준 통화: "
                        f"{currency}"
                    ),
                    (
                        f"- 거래 시장: "
                        f"{market_scope}"
                    ),
                    (
                        f"- 운용 방식: "
                        f"{strategy_type}"
                    ),
                    (
                        f"- 초기 투자재원: "
                        f"{currency_symbol}"
                        f"{initial_capital:,.0f}"
                    ),
                    (
                        f"- 현재 평가금액: "
                        f"{currency_symbol}"
                        f"{acc_eval:,.0f}"
                    ),
                    (
                        f"- 계산된 현재 현금: "
                        f"{currency_symbol}"
                        f"{acc_cash:,.0f}"
                    ),
                    (
                        f"- 월 기본 매수 한도: "
                        f"{currency_symbol}"
                        f"{base_monthly:,.0f}"
                    ),
                    (
                        f"- 시장 상황에 따른 "
                        f"월 추가 매수 한도: "
                        f"{currency_symbol}"
                        f"{max_additional:,.0f}"
                    ),
                    (
                        f"- 외부자금 납입: "
                        f"{contribution_desc}"
                    ),
                    (
                        f"- 매수 기준: "
                        f"{buy_cycle_desc}"
                    ),
                    (
                        f"- 시스템 계산 매수 가능 범위: "
                        f"{rec_desc}"
                    ),
                    "",
                ]
            )

        account_rules_str = (
            "\n".join(
                account_rule_lines
            ).strip()
            if account_rule_lines
            else "등록된 계좌별 운용 규칙 없음"
        )

        # -------------------------------------------------
        # 보유 종목
        # -------------------------------------------------

        holdings_desc = []

        for position in positions[:10]:

            target_weight = (
                float(
                    position.get(
                        "target_weight",
                        0,
                    )
                    or 0
                )
                * 100
            )

            current_weight = (
                float(
                    position.get(
                        "current_weight",
                        0,
                    )
                    or 0
                )
                * 100
            )

            pnl_pct = float(
                position.get(
                    "pl_pct",
                    0,
                )
                or 0
            )

            holdings_desc.append(
                (
                    f"- "
                    f"{position.get('name', position.get('ticker', ''))}: "
                    f"현재비중 {current_weight:.1f}% "
                    f"(목표 {target_weight:.1f}%), "
                    f"수익률 {pnl_pct:+.1f}%"
                )
            )

        holdings_str = (
            "\n".join(
                holdings_desc
            )
            if holdings_desc
            else "보유 내역 없음"
        )

        # -------------------------------------------------
        # 뉴스
        # -------------------------------------------------

        news_lines = []

        for news in news_items[:5]:

            news_lines.append(
                (
                    f"- "
                    f"[{news.get('media', '언론')}] "
                    f"{news.get('title', '')}"
                )
            )

        news_str = (
            "\n".join(
                news_lines
            )
            if news_lines
            else "최신 특이 뉴스 없음"
        )

        # -------------------------------------------------
        # 매크로
        # -------------------------------------------------

        if macro_summary:

            macro_block = (
                macro_summary
            )

            if (
                usd_krw
                and usd_krw
                not in macro_summary
            ):

                macro_block += (
                    f"\n- 원/달러 환율: "
                    f"{usd_krw}"
                )

        elif usd_krw:

            macro_block = (
                "[실시간 거시경제 지표]\n"
                f"- 원/달러 환율: "
                f"{usd_krw}"
            )

        else:

            macro_block = (
                "매크로 지표 집계 중"
            )

        # -------------------------------------------------
        # 프롬프트
        # -------------------------------------------------

        prompt = f"""
당신은 글로벌 거시경제 분석과 장기 자산배분을 지원하는 투자 분석 도우미입니다.

오늘의 시장 데이터, 실제 포트폴리오 상태, 사용자가 직접 설정한 투자 원칙,
그리고 각 계좌에 저장된 자금 운용 규칙을 구분하여 분석하세요.

절대로 '월 기본 매수 한도'를 '매달 새로 입금되는 돈'으로 해석하지 마세요.

월 기본 매수 한도는 이미 계좌 안에 존재하는 투자재원에서
한 달 동안 기본적으로 사용할 수 있는 매수 한도입니다.

월 추가 매수 한도 역시 새로운 외부 납입금이 아니라,
시장 상황에 따라 기존 계좌 자금에서 추가로 사용할 수 있는 최대 매수 한도입니다.

외부에서 새로 들어오는 자금은 반드시 각 계좌의
'외부자금 납입' 설정만을 기준으로 판단하세요.

'초기 투자재원'은 계좌 운용을 시작할 때의 투자재원이며,
현재 사용 가능한 현금과 동일하다고 가정하지 마세요.

[글로벌 매크로]
{macro_block}

[전체 포트폴리오]
- 포트폴리오: {account_name}
- 총 평가금액: {total_eval:,.0f}
- 전체 평가손익: {total_pl:,.0f}
- 전체 수익률: {total_pl_pct:+.2f}%
- 시스템 계산 현금잔액: {cash_balance:,.0f}

[사용자 전체 투자 설정]
- 투자 성향: {stance_info['label']}
- 투자 기간: {horizon_text}
- AI 조언 방식: {stance_info['label']}

[사용자가 직접 정한 투자 원칙]
{preference_text}

[계좌별 실제 자금 및 운용 규칙]
{account_rules_str}

[현재 보유 종목 및 목표비중]
{holdings_str}

[오늘의 주요 뉴스]
{news_str}

{stance_instruction}

[판단 원칙]
1. 시장 데이터와 계좌 데이터는 사용자의 자유 입력 투자 원칙보다 사실 판단에서 우선합니다.
2. 사용자의 투자 원칙은 행동 방식과 위험 선호를 개인화하는 데 사용하세요.
3. 계좌별 기준 통화, 투자 시장, 운용 방식, 매수 한도 및 외부자금 납입 방식을 서로 혼동하지 마세요.
4. KRW 계좌와 USD 계좌가 동시에 존재하면 금액을 같은 통화처럼 단순 합산하지 마세요.
5. 목표 비중이 부족하다는 이유만으로 반드시 매수하지 마세요.
6. 월 기본 매수 한도는 목표액이 아니라 상한입니다. 남은 기본 매수 가능액을 반드시 전액 사용할 필요는 없습니다.
7. 월 추가 매수 한도는 자동 매수 규칙이 아닙니다. 낙폭 조건은 추가 자금을 사용할 수 있는 범위를 여는 조건일 뿐 실제 매수 결정 자체가 아닙니다.
8. '시스템 계산 매수 가능 범위'에 표시되는 금액과 수량은 매수 명령 또는 추천 주문이 아닙니다. 현재 계좌 규칙상 사용할 수 있는 최대 범위를 나타내는 참고 데이터입니다.
9. 예산상 최대 수량과 실제 매수를 권할 수량을 구분하세요. 실제 행동은 0주(대기), 일부 매수, 또는 가능 범위 내 매수 중에서 시장 상황을 근거로 판단하세요.
10. 추가매수 여부를 판단할 때 단순 낙폭뿐 아니라 제공된 금리, 경기, 물가, 환율, 시장 추세, 뉴스 및 포트폴리오 상태를 함께 검토하세요.
11. 시장 상황상 매수 근거가 충분하지 않으면 사용 가능한 매수예산이 존재하더라도 '대기' 또는 '기본 계획 유지'를 명확히 선택하세요.
12. 반대로 장기 투자 원칙, 목표비중 괴리, 가격 조정 및 시장환경을 종합했을 때 매수가 합리적이라면 사용 가능한 범위 안에서 일부 또는 전부의 분할매수를 제시할 수 있습니다.
13. 추가매수 한도가 열렸다는 사실만으로 '저가매수 기회'라고 단정하지 마세요.
14. '초기 투자재원'과 '계산된 현재 현금'을 실제 증권사 주문가능금액과 동일하다고 단정하지 마세요.
15. 사용자가 제공하지 않은 밸류에이션이나 펀더멘털 수치를 추정하거나 만들어내지 마세요. 필요한 정보가 제공되지 않았다면 그 한계를 명시하세요.
16. 투자자의 장기 계획을 불필요한 단기 매매로 훼손하지 마세요.

[작성 지침]
차분하고 신뢰감 있는 금융 분석 문체를 사용하세요.

반드시 아래 네 필드를 포함하는 유효한 JSON 하나만 출력하세요.

- "action":
  오늘 또는 이번 매수 주기의 최종 행동 판단입니다.
  반드시 "BUY", "PARTIAL", "WAIT", "HOLD" 중 하나만 출력하세요.

  BUY:
  현재 매수 가능 범위 내에서 의미 있는 수준의 매수를 실행하는 것이 합리적이라고 판단한 경우.

  PARTIAL:
  매수 가능 범위를 전부 사용하지 않고 일부만 분할매수하는 것이 합리적이라고 판단한 경우.

  WAIT:
  매수 가능 예산이 존재하더라도 현재 시장 상황이나 매수 시점 등을 고려하여 지금은 사용하지 않고 기다리는 것이 합리적이라고 판단한 경우.

  HOLD:
  별도의 신규 매수 행동보다 기존 자산배분 및 정기 투자 계획을 그대로 유지하는 것이 합리적이라고 판단한 경우.

- "one_line_summary":
  카카오톡용 핵심 한 줄 시황 및 행동 요약.
  35~60자 정도로 작성하세요.

- "macro_analysis":
  미국 증시, 국내 증시, 환율, 유가, 국채금리, 물가 및 고용 흐름 중
  실제 제공된 데이터에서 중요한 내용을 연결하여 2~4문장으로 설명하세요.

- "strategy_advice":
  계좌별 사용 가능 매수예산, 목표비중, 현재 보유상태, 투자기간,
  사용자 투자원칙과 시장 상황을 함께 고려하여
  오늘 또는 이번 매수 주기에 무엇을 하는 것이 합리적인지 2~4문장으로 설명하세요.
  반드시 '사용 가능한 예산'과 '실제 행동 판단'을 구분하세요.
  행동은 매수, 일부 분할매수, 추가매수, 대기, 기존 계획 유지 중에서 선택할 수 있습니다.
  매수를 제시한다면 시스템의 사용 가능 예산을 초과하지 말고,
  가능한 경우 실제 매수할 금액 또는 수량을 명확히 제시하세요.
  대기를 제시한다면 사용 가능한 예산이 있더라도 왜 지금 사용하지 않는지가 드러나도록 설명하세요.
  strategy_advice의 실제 행동 내용은 반드시 action 필드와 일치해야 합니다.

one_line_summary, macro_analysis, strategy_advice에는
BUY, PARTIAL, WAIT, HOLD 같은 내부 action 코드명을 직접 표시하지 마세요.
사용자에게 보여지는 설명에서는 반드시
'매수', '일부 매수', '대기', '기존 계획 유지'와 같은 자연스러운 한국어 표현을 사용하세요.
내부 코드값은 action 필드에만 출력하세요.
제공되지 않은 시장 수치나 계좌 수치를 만들어내지 마세요.

JSON 앞뒤에 설명이나 Markdown 코드블록을 붙이지 마세요.

출력 형식:

{{
  "action": "BUY | PARTIAL | WAIT | HOLD 중 하나",
  "one_line_summary": "...",
  "macro_analysis": "...",
  "strategy_advice": "..."
}}
"""

        return prompt.strip()
        
    def _parse_json_response(self, raw_text: str) -> Dict[str, str]:
        """
        Gemini 응답 텍스트에서 JSON 객체(one_line_summary, macro_analysis, strategy_advice)를
        안전하고 유연하게 추출합니다.
        
        파싱 단계:
        1. 마크다운 코드블록(```json, ''', ``` 등) 및 부가 텍스트 제거
        2. 표준 json.loads() 및 { ... } 블록 추출 시도
        3. 따옴표 이스케이프 오류 등 JSON 문법 결함 시 정규식(Regex) 기반 필드별 개별 추출
        4. 최종 실패 시: 원본 텍스트에서 JSON 구문 및 중괄호, 키 라벨을 완전히 정제한 자연어 문장 추출 (500자 자름 없음)
        """
        clean_text = raw_text.strip()

        # 1. 마크다운 코드블록 제거 (```json, ```, '''json, ''')
        for fence in ["```json", "```JSON", "'''json", "'''JSON", "```", "'''"]:
            if fence in clean_text:
                parts = clean_text.split(fence)
                if len(parts) >= 2:
                    clean_text = parts[1]
                    for close_fence in ["```", "'''"]:
                        if close_fence in clean_text:
                            clean_text = clean_text.split(close_fence)[0]
                            break
                    clean_text = clean_text.strip()
                    break

        def _sanitize_field(text: str) -> str:
            if not text:
                return ""
            val = str(text).strip()
            for marker in ["```json", "```JSON", "'''json", "'''JSON", "```", "'''"]:
                val = val.replace(marker, "")
            val = re.sub(r'["\']?(?:one_line[_\"]?summary|macro_analysis|strategy_advice)["\']?\s*:\s*', '', val, flags=re.IGNORECASE)
            val = val.replace("{", "").replace("}", "").strip()
            lines = [l.strip().strip('",\'') for l in val.splitlines() if l.strip().strip('",\'')]
            return "\n".join(lines).strip()

        # 2-1. 직접 json.loads 시도
        try:
            parsed = json.loads(clean_text)
            if isinstance(parsed, dict) and "macro_analysis" in parsed:
                return {
                    "action": str(
                        parsed.get(
                            "action",
                            "HOLD",
                        )
                        or "HOLD"
                    ).strip().upper(),
                    "one_line_summary": _sanitize_field(
                        parsed.get(
                            "one_line_summary",
                            "",
                        )
                    ),
                    "macro_analysis": _sanitize_field(
                        parsed.get(
                            "macro_analysis",
                            "",
                        )
                    ),
                    "strategy_advice": _sanitize_field(
                        parsed.get(
                            "strategy_advice",
                            "",
                        )
                    ),
                }
        except Exception:
            pass

        # 2-2. { ... } 블록 슬라이싱 후 시도
        start = clean_text.find("{")
        end = clean_text.rfind("}")
        if start != -1 and end != -1 and end > start:
            sub = clean_text[start : end + 1]
            try:
                parsed = json.loads(sub)
                if isinstance(parsed, dict) and "macro_analysis" in parsed:
                    return {
                        "action": str(
                            parsed.get(
                                "action",
                                "HOLD",
                            )
                            or "HOLD"
                        ).strip().upper(),
                        "one_line_summary": _sanitize_field(
                            parsed.get(
                                "one_line_summary",
                                "",
                            )
                        ),
                        "macro_analysis": _sanitize_field(
                            parsed.get(
                                "macro_analysis",
                                "",
                            )
                        ),
                        "strategy_advice": _sanitize_field(
                            parsed.get(
                                "strategy_advice",
                                "",
                            )
                        ),
                    }
            except Exception:
                try:
                    fixed_sub = re.sub(
                        r",\s*([\]}])",
                        r"\1",
                        sub,
                    )
            
                    parsed = json.loads(
                        fixed_sub
                    )
            
                    if (
                        isinstance(parsed, dict)
                        and "macro_analysis" in parsed
                    ):
                        return {
                            "action": str(
                                parsed.get(
                                    "action",
                                    "HOLD",
                                )
                                or "HOLD"
                            ).strip().upper(),
            
                            "one_line_summary":
                                _sanitize_field(
                                    parsed.get(
                                        "one_line_summary",
                                        "",
                                    )
                                ),
            
                            "macro_analysis":
                                _sanitize_field(
                                    parsed.get(
                                        "macro_analysis",
                                        "",
                                    )
                                ),
            
                            "strategy_advice":
                                _sanitize_field(
                                    parsed.get(
                                        "strategy_advice",
                                        "",
                                    )
                                ),
                        }
            
                except Exception:
                    pass

        # 3. 정규식 기반 개별 필드 추출
        # JSON 문법이 일부 깨진 경우에도
        # action / one_line_summary / macro_analysis /
        # strategy_advice를 최대한 복구합니다.

        action = "HOLD"
        one_line = ""
        macro_text = ""
        strategy_text = ""

        # action 복구
        action_match = re.search(
            r'["\']?action["\']?\s*:\s*["\']?'
            r'(BUY|PARTIAL|WAIT|HOLD)'
            r'["\']?',
            clean_text,
            re.IGNORECASE,
        )

        if action_match:
            action = (
                action_match
                .group(1)
                .strip()
                .upper()
            )

        m1 = re.search(
            r'["\']?one_line[_\"]?summary["\']?\s*:\s*["\']?'
            r'(.*?)'
            r'(?:["\']?\s*,\s*["\']?macro_analysis|'
            r'\n\s*["\']?macro_analysis|\Z)',
            clean_text,
            re.DOTALL | re.IGNORECASE,
        )

        if m1:
            one_line = (
                m1.group(1)
                .strip()
                .strip('"\' ,\r\n')
            )

        m2 = re.search(
            r'["\']?macro_analysis["\']?\s*:\s*["\']?'
            r'(.*?)'
            r'(?:["\']?\s*,\s*["\']?strategy_advice|'
            r'\n\s*["\']?strategy_advice|\Z)',
            clean_text,
            re.DOTALL | re.IGNORECASE,
        )

        if m2:
            macro_text = (
                m2.group(1)
                .strip()
                .strip('"\' ,\r\n')
            )

        m3 = re.search(
            r'["\']?strategy_advice["\']?\s*:\s*["\']?'
            r'(.*?)'
            r'(?:["\']?\s*\}|\n\s*\}|\Z)',
            clean_text,
            re.DOTALL | re.IGNORECASE,
        )

        if m3:
            strategy_text = (
                m3.group(1)
                .strip()
                .strip('"\' ,}\r\n')
            )

        stance_info = (
            INVESTMENT_STANCE_PROFILES.get(
                self.investment_stance,
                INVESTMENT_STANCE_PROFILES[
                    "balanced"
                ],
            )
        )

        fallback_adv = stance_info.get(
            "fallback_advice",
            (
                "원칙에 기반한 정기 분할 매수 "
                "전략을 유지하시기 바랍니다."
            ),
        )

        if macro_text:
            macro_text = _sanitize_field(
                macro_text
                .replace('\\"', '"')
                .replace('\\n', '\n')
            )

            strategy_text = _sanitize_field(
                strategy_text
                .replace('\\"', '"')
                .replace('\\n', '\n')
            )

            one_line = _sanitize_field(
                one_line.replace(
                    '\\"',
                    '"',
                )
            )

            return {
                "action": action,
                "one_line_summary": (
                    one_line
                    or
                    "📈 글로벌 매크로 지표 분석이 반영되었습니다."
                ),
                "macro_analysis":
                    macro_text,
                "strategy_advice": (
                    strategy_text
                    or fallback_adv
                ),
            }
            
        # 4. 최종 Fallback: JSON 키나 마크다운 기호가 노출되지 않도록 완전히 정제된 자연어 텍스트 추출 (500자 잘림 방지)
        sanitized = raw_text
        for tag in ["```json", "```JSON", "'''json", "'''JSON", "```", "'''"]:
            sanitized = sanitized.replace(tag, "")
        sanitized = re.sub(r'["\']?(?:one_line[_\"]?summary|macro_analysis|strategy_advice)["\']?\s*:\s*', '', sanitized, flags=re.IGNORECASE)
        sanitized = sanitized.replace("{", "").replace("}", "").strip()
        lines = [line.strip().strip('",\'') for line in sanitized.splitlines() if line.strip().strip('",\'')]
        clean_prose = "\n".join(lines).strip()

        first_line = lines[0] if lines else "🌅 글로벌 매크로 & 시장 분석 요약입니다."
        body_text = "\n".join(lines[1:]) if len(lines) > 1 else clean_prose

        return {
            "action": action,
            "one_line_summary": (
                _sanitize_field(one_line)
                or _sanitize_field(first_line)
            ),
            "macro_analysis": _sanitize_field(
                body_text
                or clean_prose
            ),
            "strategy_advice":
                fallback_adv,
        }
