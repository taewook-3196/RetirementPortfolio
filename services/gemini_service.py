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
        "short_desc": "정석 퀀트 자산배분 / 원칙 준수",
        "description": "정석 퀀트 자산배분. 매크로 지표를 객관적으로 분석하고 정해진 주기 및 목표 비중 괴리도 공식에 따라 기계적 분할 매수 원칙을 준수합니다.",
        "prompt_instruction": (
            "[투자자 맞춤 투자 성향: '중립적 / 균형 (정석 퀀트 자산배분)']\n"
            "- 투자자는 감정을 배제하고 장기 자산배분 퀀트 원칙을 충실히 따릅니다.\n"
            "- 조언 지침:\n"
            "  1) 매크로 지표의 상승/하락 트렌드를 가감 없이 객관적으로 요약하세요.\n"
            "  2) 목표 비중 대비 괴리도가 큰 1순위 추천 종목을 기계적으로 분할 매수하여 전체 포트폴리오의 균형을 맞추도록 조언하세요.\n"
            "  3) '정해진 규칙과 원칙을 지키는 꾸준한 적립식 투자가 장기 승리의 열쇠입니다'와 같은 정석적인 어조로 조언하세요."
        ),
        "fallback_advice": "정해진 주기와 괴리도 공식에 따라 목표 비중 미달 종목을 규칙적으로 분할 매수하시기 바랍니다.",
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
        prompt = self._build_prompt(report_context, macro_summary)

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
        return {
            "success": True,
            "model_used": used_model,
            "investment_stance": self.investment_stance,
            "stance_badge": stance_info["badge"],
            "stance_label": stance_info["label"],
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
        """프리미엄 투자 가이드 생성을 위한 정교한 프롬프트 구성"""
        summary = ctx.get("summary", {})
        recommendations = ctx.get("recommendations", {})
        positions = ctx.get("positions", [])
        news_items = ctx.get("news", [])
        account_name = ctx.get("account_name", "퇴직연금 IRP/연금저축")

        # 사용자별 투자 성향 및 자유 입력 투자 원칙
        investment_profile = (
            ctx.get("investment_profile")
            or {}
        )

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

        monthly_investment = float(
            investment_profile.get(
                "monthly_investment",
                0,
            )
            or 0
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

        total_eval = summary.get("total_eval", 0)
        total_pl = summary.get("total_pl", 0)
        total_pl_pct = summary.get("total_pl_pct", 0.0)
        cash_balance = summary.get("cash_balance", 0)

        d_day = recommendations.get("d_day", None)
        next_buy_date = recommendations.get("next_buy_date", "")
        rec_items = recommendations.get("items", [])
        top_rec = rec_items[0] if rec_items else {}

        # 보유 종목 요약
        holdings_desc = []
        for p in positions[:5]:
            t_w = p.get("target_weight", 0) * 100
            c_w = p.get("current_weight", 0) * 100
            holdings_desc.append(f"- {p.get('name')}: 현재비중 {c_w:.1f}% (목표: {t_w:.1f}%), 수익률: {p.get('pl_pct', 0):+.1f}%")
        holdings_str = "\n".join(holdings_desc) if holdings_desc else "보유 내역 없음"

        # 뉴스 헤드라인 요약
        news_lines = []
        for n in news_items[:5]:
            news_lines.append(f"- [{n.get('media', '언론')}] {n.get('title', '')}")
        news_str = "\n".join(news_lines) if news_lines else "최신 특이 뉴스 없음"

        if macro_summary:
            macro_block = macro_summary
            if usd_krw and usd_krw not in macro_summary:
                macro_block += f"\n- 실시간 환율: {usd_krw}"
        elif usd_krw:
            macro_block = f"[실시간 거시경제 지표]\n- 원/달러 환율: {usd_krw}"
        else:
            macro_block = "매크로 지표 집계 중"

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
            stance_info["prompt_instruction"]
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

        prompt = f"""
당신은 최고 권위의 글로벌 거시경제(매크로) 분석가이자, 장기 은퇴/퇴직연금 분할매수 퀀트 포트폴리오 매니저입니다.
투자자의 계좌 정보, 글로벌 지표, 환율, 수집된 뉴스를 종합하여 매일 아침 출근길에 읽기 좋은 명쾌하고 신뢰감 넘치는 모닝 브리핑을 작성하세요.

{macro_block}

[현재 계좌 및 포트폴리오 상황]
- 계좌명: {account_name}
- 총 평가자산: {total_eval:,.0f}원 (수익률: {total_pl_pct:+.2f}%, 평가손익: {total_pl:,.0f}원)
- 예수금(현금): {cash_balance:,.0f}원
- 매수 주기 현황: 매수 D-{d_day}일 남음 (정기 매수 예정일: {next_buy_date})
- 1순위 추천 매수 종목: {top_rec.get('name', '비중 안정적 유지')} ({top_rec.get('recommended_shares', 0)}주 추천, 추천사유: {top_rec.get('reason', '')})

[보유 종목 비중 현황]
{holdings_str}

[사용자 개인 투자 설정]
- 투자 성향: {stance_info['label']}
- 투자 기간: {horizon_text}
- 월 투자 가능금액: {monthly_investment:,.0f}원
- AI 조언 방식: {stance_info['label']}

[사용자가 직접 정한 투자 원칙 / 전략]
{preference_text}

중요:
- 위 사용자의 투자 원칙과 투자 기간을 개인화 조언에 적극 반영하세요.
- 사용자의 자유 입력 원칙은 투자 선호사항이지 시장의 사실 데이터가 아닙니다.
- 사용자 원칙이 실제 시장 데이터, 계좌 데이터 또는 계산된 포트폴리오 수치와 충돌하면 사실 데이터를 왜곡하지 마세요.
- 사용자의 원칙과 시스템이 계산한 목표 비중 및 매수 가능금액을 함께 고려하세요.

[오늘의 주요 뉴스 헤드라인]
{news_str}

{stance_instruction}

[작성 지침]
1. 어투: 차분하고 신뢰감을 주는 금융 전문가의 어조 (~합니다, ~바람직합니다).
2. 위 글로벌 10대 지표(미국 3대 증시, 국내 지수, 환율, WTI 유가, 10년물 국채금리, PCE 물가 및 고용지표)의 '상승/하락/보합 트렌드'를 유기적으로 연결하여 시장 분위기를 분석하세요.
3. 세 가지 항목을 반드시 포함하여 유효한 JSON 형식으로만 응답해야 합니다:
   - "one_line_summary": 스마트폰 카카오톡 알림용 핵심 한 줄 브리핑 (이모지 포함, 35~50자 내외로 지표 흐름과 추천을 찌르는 문장).
   - "macro_analysis": 글로벌 매크로 및 시황 분석 (환율/유가/국채금리 추세와 미 증시 흐름이 국내 및 퇴직연금 ETF에 미치는 영향 2~3문장).
   - "strategy_advice": 내 계좌 맞춤 분할 매수 조언 (투자자의 성향 '{stance_info['label']}'에 부합하는 행동 지침을 명확히 반영하며, 목표 비중 괴리도와 1순위 추천 종목을 검토하되, 시장 상황과 사용자의 투자 원칙을 함께 고려하여 매수·대기·분할매수 중 적절한 행동을 설명하는 코멘트 2~3문장).
4. JSON 값 내부 텍스트에는 큰따옴표(") 대신 작은따옴표(')를 사용하거나 큰따옴표를 이스케이프(\")하여 유효한 JSON 구문을 유지하세요. 앞뒤 부가 설명 없이 순수 JSON만 출력하세요.

[출력 JSON 스키마 예시]
```json
{{
  "one_line_summary": "📈 나스닥 강세와 유가 하락 안정 속, D-4일 TDF 및 분할 매수 적기입니다.",
  "macro_analysis": "미국 증시는 기술주 호조로 나스닥 중심의 상승세를 이어갔으며, 국제 유가(WTI) 하락으로 인플레이션 부담이 완화되고 있습니다. 근원 PCE와 금리 추세가 안정세를 유지하여 해외 지수 추종 및 자산배분 ETF에 우호적인 환경입니다.",
  "strategy_advice": "현재 목표 비중 대비 저평가된 '{top_rec.get('name', '자산배분 ETF')}'을(를) 중심으로 계획된 분할 매수를 이어가는 것이 유리합니다. 거시경제 지표 안정세 속에서 원칙을 지키는 정석 투자를 권장합니다."
}}
```
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
                    "one_line_summary": _sanitize_field(parsed.get("one_line_summary", "")),
                    "macro_analysis": _sanitize_field(parsed.get("macro_analysis", "")),
                    "strategy_advice": _sanitize_field(parsed.get("strategy_advice", "")),
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
                        "one_line_summary": _sanitize_field(parsed.get("one_line_summary", "")),
                        "macro_analysis": _sanitize_field(parsed.get("macro_analysis", "")),
                        "strategy_advice": _sanitize_field(parsed.get("strategy_advice", "")),
                    }
            except Exception:
                try:
                    fixed_sub = re.sub(r",\s*([\]}])", r"\1", sub)
                    parsed = json.loads(fixed_sub)
                    if isinstance(parsed, dict) and "macro_analysis" in parsed:
                        return {
                            "one_line_summary": _sanitize_field(parsed.get("one_line_summary", "")),
                            "macro_analysis": _sanitize_field(parsed.get("macro_analysis", "")),
                            "strategy_advice": _sanitize_field(parsed.get("strategy_advice", "")),
                        }
                except Exception:
                    pass

        # 3. 정규식 기반 개별 필드 추출 (따옴표 오류나 오탈자("one_line"summary 등) 발생 시에도 완벽 복구)
        one_line = ""
        macro_text = ""
        strategy_text = ""

        m1 = re.search(
            r'["\']?one_line[_\"]?summary["\']?\s*:\s*["\']?(.*?)(?:["\']?\s*,\s*["\']?macro_analysis|\n\s*["\']?macro_analysis|\Z)',
            clean_text,
            re.DOTALL | re.IGNORECASE,
        )
        if m1:
            one_line = m1.group(1).strip().strip('"\' ,\r\n')

        m2 = re.search(
            r'["\']?macro_analysis["\']?\s*:\s*["\']?(.*?)(?:["\']?\s*,\s*["\']?strategy_advice|\n\s*["\']?strategy_advice|\Z)',
            clean_text,
            re.DOTALL | re.IGNORECASE,
        )
        if m2:
            macro_text = m2.group(1).strip().strip('"\' ,\r\n')

        m3 = re.search(
            r'["\']?strategy_advice["\']?\s*:\s*["\']?(.*?)(?:["\']?\s*\}|\n\s*\}|\Z)',
            clean_text,
            re.DOTALL | re.IGNORECASE,
        )
        if m3:
            strategy_text = m3.group(1).strip().strip('"\' ,}\r\n')

        stance_info = INVESTMENT_STANCE_PROFILES.get(self.investment_stance, INVESTMENT_STANCE_PROFILES["balanced"])
        fallback_adv = stance_info.get("fallback_advice", "원칙에 기반한 정기 분할 매수 전략을 유지하시기 바랍니다.")

        if macro_text:
            macro_text = _sanitize_field(macro_text.replace('\\"', '"').replace('\\n', '\n'))
            strategy_text = _sanitize_field(strategy_text.replace('\\"', '"').replace('\\n', '\n'))
            one_line = _sanitize_field(one_line.replace('\\"', '"'))
            return {
                "one_line_summary": one_line or "📈 글로벌 매크로 지표 분석이 반영되었습니다.",
                "macro_analysis": macro_text,
                "strategy_advice": strategy_text or fallback_adv,
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
            "one_line_summary": _sanitize_field(one_line) or _sanitize_field(first_line),
            "macro_analysis": _sanitize_field(body_text or clean_prose),
            "strategy_advice": fallback_adv,
        }
