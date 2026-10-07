"""
services/kakao_service.py
카카오톡 '나에게 보내기' REST API 연동 및 자동 토큰 갱신 서비스.
- 카카오 메시지 API (POST https://kapi.kakao.com/v2/api/talk/memo/default/send)
- 모바일 웹 리포트 링크 버튼이 포함된 텍스트 템플릿 메시지 발송
- Refresh Token 기반 Access Token 자동 갱신 및 config.yaml 자동 동기화
- 카카오 API 키 및 토큰 유효성 검사/테스트 발송 지원
"""

from __future__ import annotations
import copy
import json
import logging
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, Tuple
from core.secret_crypto import decrypt_secret, encrypt_secret
from core.config import (
    AppConfig,
    MorningReportConfig,
    get_report_url,
    save_config,
    validate_public_url,
)

logger = logging.getLogger("RetirementPortfolio.KakaoService")


class KakaoService:
    """카카오톡 '나에게 보내기' API 클라이언트"""

    SEND_MEMO_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    TOKEN_REFRESH_URL = "https://kauth.kakao.com/oauth/token"

    def __init__(self, config: AppConfig):
        self.config = config
        self.morning_cfg: MorningReportConfig = getattr(config, "morning_report", MorningReportConfig())


    @classmethod
    def for_user(cls, config: AppConfig, repo):
        """Build a Kakao client from this user's encrypted OAuth credentials."""
        # Never mutate the shared AppConfig used by the multi-user runner.
        # Start every user with blank Kakao tokens so a user without a
        # credential cannot inherit legacy/global or a previous user's token.
        user_config = copy.deepcopy(config)
        instance = cls(user_config)
        instance.morning_cfg.kakao_rest_api_key = __import__("os").getenv("KAKAO_REST_API_KEY", "").strip()
        instance.morning_cfg.kakao_access_token = ""
        instance.morning_cfg.kakao_refresh_token = ""
        instance._credential_repo = repo

        credential = repo.get_kakao_credential()
        # unittest.mock.Mock fabricates arbitrary attributes on access. Only
        # accept the concrete string fields that a persisted credential has.
        access_encrypted = getattr(credential, "access_token_encrypted", None) if credential is not None else None
        refresh_encrypted = getattr(credential, "refresh_token_encrypted", None) if credential is not None else None
        if not isinstance(access_encrypted, str) or not access_encrypted:
            return instance
        if not isinstance(refresh_encrypted, str) or not refresh_encrypted:
            return instance
        instance.morning_cfg.kakao_access_token = decrypt_secret(access_encrypted)
        instance.morning_cfg.kakao_refresh_token = decrypt_secret(refresh_encrypted)
        return instance

    def is_configured(self) -> bool:
        """카카오 API 키 또는 Access Token 설정 여부 확인"""
        return bool(self.morning_cfg.kakao_access_token.strip())

    def refresh_access_token(self) -> Tuple[bool, str]:
        """
        Refresh Token을 사용하여 만료된 Access Token을 자동 갱신합니다.
        성공 시 새로운 토큰을 AppConfig 및 config.yaml에 즉시 반영 저장합니다.
        """
        client_id = self.morning_cfg.kakao_rest_api_key.strip()
        refresh_token = self.morning_cfg.kakao_refresh_token.strip()

        if not client_id or not refresh_token:
            return False, "REST API 키 또는 Refresh Token이 설정되어 있지 않습니다."

        data = urllib.parse.urlencode({
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": refresh_token,
        }).encode("utf-8")

        req = urllib.request.Request(
            self.TOKEN_REFRESH_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                new_access = result.get("access_token")
                new_refresh = result.get("refresh_token")

                if new_access:
                    self.morning_cfg.kakao_access_token = new_access
                    if new_refresh:
                        self.morning_cfg.kakao_refresh_token = new_refresh
                    
                    credential_repo = getattr(self, "_credential_repo", None)
                    if credential_repo is not None:
                        existing = credential_repo.get_kakao_credential()
                        now = datetime.now(timezone.utc)
                        expires_in = int(result.get("expires_in", 0) or 0)
                        refresh_expires_in = int(result.get("refresh_token_expires_in", 0) or 0)
                        credential_repo.save_kakao_credential(
                            access_token_encrypted=encrypt_secret(new_access),
                            refresh_token_encrypted=encrypt_secret(new_refresh or refresh_token),
                            access_token_expires_at=(
                                now + timedelta(seconds=expires_in)
                                if expires_in else getattr(existing, "access_token_expires_at", None)
                            ),
                            refresh_token_expires_at=(
                                now + timedelta(seconds=refresh_expires_in)
                                if new_refresh and refresh_expires_in
                                else getattr(existing, "refresh_token_expires_at", None)
                            ),
                            scopes=getattr(existing, "scopes", "") or "",
                        )
                    else:
                        save_config(self.config)
                    logger.info("카카오톡 Access Token 자동 갱신 성공")
                    return True, "토큰 갱신 성공"
                else:
                    return False, f"갱신 응답 오류: {result}"
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8", errors="ignore")
            logger.error(f"카카오 토큰 갱신 HTTP 오류 ({e.code}): {err_msg}")
            return False, f"HTTP {e.code}: {err_msg}"
        except Exception as e:
            logger.error(f"카카오 토큰 갱신 실패: {e}")
            return False, str(e)

    def send_memo_text_button(
        self,
        text_content: str,
        web_url: str,
        button_title: str = "📊 모바일 리포트 열기",
        *,
        allow_token_refresh: bool = True,
    ) -> Tuple[bool, str]:
        """
        카카오 '나에게 보내기' API로 텍스트 + 웹 링크 버튼 메시지를 전송합니다.
        401 (만료) 발생 시 자동으로 refresh_access_token()을 시도한 후 재전송합니다.
        """
        access_token = self.morning_cfg.kakao_access_token.strip()
        if not access_token:
            return False, "카카오 Access Token이 비어있습니다. [환경 설정]에서 토큰을 입력해 주세요."

        # 카카오는 공개 HTTP(S) 링크만 지원합니다.
        safe_url = validate_public_url(web_url, get_report_url())

        template_obj = {
            "object_type": "text",
            "text": text_content,
            "link": {
                "web_url": safe_url,
                "mobile_web_url": safe_url,
            },
            "button_title": button_title,
            "buttons": [
                {
                    "title": button_title,
                    "link": {
                        "web_url": safe_url,
                        "mobile_web_url": safe_url,
                    },
                }
            ],
        }

        payload = urllib.parse.urlencode({
            "template_object": json.dumps(template_obj, ensure_ascii=False)
        }).encode("utf-8")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) RetirementPortfolio/1.0",
        }

        req = urllib.request.Request(self.SEND_MEMO_URL, data=payload, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    if resp_data.get("result_code") == 0:
                        return True, "카카오톡 메시지 전송 성공!"
                    return False, f"API 응답 코드 이상: {resp_data}"
        except urllib.error.HTTPError as e:
            # 토큰 만료(401)인 경우 1회 자동 갱신 시도
            if (
                e.code == 401
                and allow_token_refresh
                and self.morning_cfg.kakao_refresh_token.strip()
            ):
                logger.warning("Access Token 만료 감지, Refresh Token으로 자동 갱신 시도...")
                refreshed, ref_msg = self.refresh_access_token()
                if refreshed:
                    # 갱신된 토큰으로 재전송
                    return self.send_memo_text_button(
                        text_content,
                        web_url,
                        button_title,
                        allow_token_refresh=False,
                    )
                else:
                    return False, f"토큰 만료 및 자동 갱신 실패: {ref_msg}"

            err_body = e.read().decode("utf-8", errors="ignore")
            logger.error(f"카카오톡 전송 실패 HTTP {e.code}: {err_body}")

            if e.code == 403:
                try:
                    error_data = json.loads(err_body)
                except (TypeError, ValueError):
                    error_data = {}
                required_scopes = error_data.get("required_scopes") or []
                if error_data.get("code") == -402 and "talk_message" in required_scopes:
                    return False, (
                        "카카오톡 메시지 전송 권한이 없습니다. "
                        "'카카오톡 다시 연결'을 눌러 "
                        "'카카오톡 메시지 전송' 항목에 동의해주세요."
                    )

            return False, f"카카오 API 오류 (HTTP {e.code}): {err_body}"
        except Exception as e:
            logger.error(f"카카오톡 전송 중 예외 발생: {e}")
            return False, f"네트워크 오류: {str(e)}"

        return False, "알 수 없는 오류로 발송되지 않았습니다."

    def send_morning_report(
        self,
        summary_text: str,
        web_url: str
    ) -> Tuple[bool, str]:
        """모닝 리포트 요약 카드 및 웹 링크 발송"""
        return self.send_memo_text_button(
            text_content=summary_text,
            web_url=web_url,
            button_title="📊 모바일 상세 리포트 열기"
        )

    def send_test_message(self, web_url: str = "https://finance.naver.com") -> Tuple[bool, str]:
        """연결 테스트 메시지 발송"""
        test_text = (
            "🔔 [포트폴리오 매니저] 카카오톡 연동 테스트\n\n"
            "카카오톡 메시지 발송 기능이 정상적으로 연결되었습니다!\n"
            "매일 아침 설정하신 시간에 모닝 리포트와 모바일 웹 링크가 발송됩니다."
        )
        return self.send_memo_text_button(
            text_content=test_text,
            web_url=web_url,
            button_title="📱 테스트 리포트 확인"
        )
