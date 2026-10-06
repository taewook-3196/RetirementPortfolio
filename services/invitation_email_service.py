"""Invitation email delivery.

Uses Resend's HTTPS API when configured. Secrets stay server-side and are never
returned to the browser or written to application logs.
"""
from __future__ import annotations

import json
import os
import requests


class InvitationEmailError(RuntimeError):
    pass


def invitation_email_configured() -> bool:
    return bool(
        os.getenv("RESEND_API_KEY", "").strip()
        and os.getenv("INVITE_EMAIL_FROM", "").strip()
    )


def _send_payload(payload: dict) -> str:
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    try:
        response = requests.post(
            "https://api.resend.com/emails",
            json=payload,
            headers={
                "Authorization": "Bearer " + api_key,
                "User-Agent": "RetirementPortfolio/1.0",
            },
            timeout=12,
        )
    except requests.RequestException as exc:
        raise InvitationEmailError("Resend에 연결하지 못했습니다.") from exc
    if not response.ok:
        provider_message = ""
        try:
            provider_message = str(response.json().get("message") or "").strip()
        except (ValueError, AttributeError):
            pass
        detail = f"Resend HTTP {response.status_code}"
        if provider_message:
            detail += f": {provider_message}"
        raise InvitationEmailError(detail)
    try:
        data = response.json()
    except ValueError as exc:
        raise InvitationEmailError("Resend 응답을 해석하지 못했습니다.") from exc
    message_id = str(data.get("id") or "").strip()
    if not message_id:
        raise InvitationEmailError("이메일 발송 결과를 확인하지 못했습니다.")
    return message_id


def send_invitation_email(*, recipient: str, invite_url: str, expires_at: str) -> str:
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    sender = os.getenv("INVITE_EMAIL_FROM", "").strip()
    if not api_key or not sender:
        raise InvitationEmailError("초대 이메일 발송 설정이 완료되지 않았습니다.")
    text_body = (
        "RetirementPortfolio에 초대되었습니다.\n\n"
        f"회원가입: {invite_url}\n"
        f"초대 만료: {expires_at}\n\n"
        "투자 데이터는 사용자 계정별로 분리되어 관리되며 관리자 화면에서는 "
        "회원의 보유종목, 투자금액, 매매내역 등 개인 투자정보를 열람할 수 없습니다.\n\n"
        "실제 계좌번호 전체, 증권사 비밀번호, 인증번호, API 비밀키 등 "
        "민감한 인증정보는 RetirementPortfolio에 입력하지 마세요."
    )
    return _send_payload({
        "from": sender,
        "to": [recipient],
        "subject": "RetirementPortfolio 초대",
        "text": text_body,
    })


def send_resend_diagnostic_email() -> str:
    """Send only to Resend's official delivered test recipient."""
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    sender = os.getenv("INVITE_EMAIL_FROM", "").strip()
    if not api_key or not sender:
        raise InvitationEmailError("초대 이메일 발송 설정이 완료되지 않았습니다.")
    return _send_payload({
        "from": sender,
        "to": ["delivered@resend.dev"],
        "subject": "RetirementPortfolio Resend diagnostic",
        "text": "RetirementPortfolio email delivery configuration test.",
    })
