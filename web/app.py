"""
web/app.py

RetirementPortfolio 모바일 웹 애플리케이션.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone, timedelta
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from supabase import create_client
from services.portfolio_service import PortfolioService
from services.kakao_service import KakaoService
from core.secret_crypto import encrypt_secret
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from database.connection import get_db_session
from database.models import Profile, DeletedMember, AppSetting, KakaoCredential, UserSetting
from database.repository import Repository
from portfolio.holdings import calculate_etf_positions
from data.yfinance_client import YFinanceClient

app = FastAPI(
    title="RetirementPortfolio",
    version="0.7.0",
)


# =========================================================
# 공통 인증
# =========================================================

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "RetirementPortfolio",
    }


@app.get("/api/me")
def get_current_user(
    authorization: str | None = Header(default=None),
):
    """로그인한 Supabase 사용자를 확인합니다."""

    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="로그인이 필요합니다.",
        )

    scheme, separator, token = authorization.partition(" ")

    if (
        not separator
        or scheme.lower() != "bearer"
        or not token.strip()
    ):
        raise HTTPException(
            status_code=401,
            detail="올바른 인증 토큰이 필요합니다.",
        )

    supabase_url = os.getenv(
        "SUPABASE_URL",
        "",
    ).strip()

    supabase_key = os.getenv(
        "SUPABASE_ANON_KEY",
        "",
    ).strip()

    if not supabase_url or not supabase_key:
        raise HTTPException(
            status_code=500,
            detail="Supabase 인증 설정이 없습니다.",
        )

    try:
        supabase = create_client(
            supabase_url,
            supabase_key,
        )

        response = supabase.auth.get_user(
            token.strip()
        )

        user = response.user

        if user is None:
            raise HTTPException(
                status_code=401,
                detail="유효하지 않은 로그인입니다.",
            )

        with get_db_session() as db:
            profile = db.query(Profile).filter(Profile.id == UUID(str(user.id))).one_or_none()
            if profile is None:
                raise HTTPException(
                    status_code=403,
                    detail="회원 정보가 등록되지 않은 계정입니다. 관리자에게 문의해 주세요.",
                )
            if not bool(profile.is_active):
                raise HTTPException(status_code=403, detail="관리자에 의해 사용이 중지된 계정입니다.")

        return {
            "authenticated": True,
            "user_id": str(user.id),
            "email": user.email,
        }

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=401,
            detail="로그인이 만료되었거나 유효하지 않습니다.",
        )


def get_verified_user_id(
    authorization: str | None,
) -> str:
    user = get_current_user(
        authorization=authorization
    )

    return user["user_id"]


def require_admin(
    authorization: str | None,
) -> dict:
    """Require application admin membership without granting portfolio access."""
    user = get_current_user(authorization=authorization)

    with get_db_session() as db:
        profile = (
            db.query(Profile)
            .filter(Profile.id == UUID(str(user["user_id"])))
            .one_or_none()
        )

        if profile is None or not bool(profile.is_admin):
            raise HTTPException(
                status_code=403,
                detail="관리자 권한이 필요합니다.",
            )

    return user


@app.get("/api/admin/me")
def get_admin_status(
    authorization: str | None = Header(default=None),
):
    """Return admin status only after server-side authorization."""
    user = require_admin(authorization)
    return {
        "authenticated": True,
        "is_admin": True,
        "user_id": user["user_id"],
        "email": user["email"],
    }


SIGNUP_ENABLED_KEY = "signup_enabled"


def _signup_enabled() -> bool:
    with get_db_session() as db:
        row = db.query(AppSetting).filter(AppSetting.key == SIGNUP_ENABLED_KEY).one_or_none()
        return bool(row and str(row.value).strip().lower() == "true")


class SignupControlRequest(BaseModel):
    enabled: bool


@app.get("/api/signup-status")
def get_signup_status():
    return {"signup_enabled": _signup_enabled()}


@app.put("/api/admin/signup-status")
def set_signup_status(
    request: SignupControlRequest,
    authorization: str | None = Header(default=None),
):
    require_admin(authorization)
    with get_db_session() as db:
        row = db.query(AppSetting).filter(AppSetting.key == SIGNUP_ENABLED_KEY).one_or_none()
        value = "true" if request.enabled else "false"
        if row is None:
            db.add(AppSetting(key=SIGNUP_ENABLED_KEY, value=value))
        else:
            row.value = value
            row.updated_at = datetime.now(timezone.utc)
    return {"signup_enabled": request.enabled}


def _get_supabase_admin_client():
    supabase_url = os.getenv("SUPABASE_URL", "").strip()
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not supabase_url or not service_key:
        raise HTTPException(
            status_code=500,
            detail="Supabase 관리자 설정이 없습니다.",
        )
    return create_client(supabase_url, service_key)


@app.get("/api/admin/members")
def list_admin_members(
    authorization: str | None = Header(default=None),
):
    """List operational membership status without exposing portfolio data."""
    require_admin(authorization)
    admin_client = _get_supabase_admin_client()

    try:
        response = admin_client.auth.admin.list_users()
        auth_users = getattr(response, "users", response)
        auth_users = list(auth_users or [])
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="회원 목록을 불러오지 못했습니다.",
        )

    with get_db_session() as db:
        profiles = {str(p.id): p for p in db.query(Profile).all()}
        kakao_ids = {
            str(row.user_id)
            for row in db.query(KakaoCredential.user_id).all()
        }
        settings = {
            str(row.user_id): row
            for row in db.query(UserSetting).all()
        }

    members = []
    for user in auth_users:
        user_id = str(getattr(user, "id", "") or "")
        profile = profiles.get(user_id)
        setting = settings.get(user_id)
        members.append({
            "user_id": user_id,
            "email": getattr(user, "email", None),
            "created_at": (
                getattr(user, "created_at", None).isoformat()
                if hasattr(getattr(user, "created_at", None), "isoformat")
                else str(getattr(user, "created_at", "") or "") or None
            ),
            "is_admin": bool(profile and profile.is_admin),
            "is_active": bool(profile.is_active) if profile else False,
            "kakao_connected": user_id in kakao_ids,
            "morning_report_enabled": (
                bool(setting.morning_report_enabled) if setting else False
            ),
        })

    return {
        "members": members,
        "privacy_scope": (
            "관리자에게는 회원 운영 상태만 제공되며 보유종목, 수량, 평가금액, "
            "거래내역, 현금잔고, 투자성향, 모닝리포트 내용은 제공되지 않습니다."
        ),
    }


def _has_retained_member_data(user_id: UUID) -> bool:
    """Return only whether deleted-member private data remains, never its contents."""
    from database.models import (
        Account, InvestmentProfile, Watchlist, MorningReport, RecommendationLog,
    )

    with get_db_session() as db:
        checks = (
            db.query(Account.id).filter(Account.user_id == user_id).first(),
            db.query(InvestmentProfile.id).filter(InvestmentProfile.user_id == user_id).first(),
            db.query(Watchlist.id).filter(Watchlist.user_id == user_id).first(),
            db.query(UserSetting.id).filter(UserSetting.user_id == user_id).first(),
            db.query(KakaoCredential.id).filter(KakaoCredential.user_id == user_id).first(),
            db.query(MorningReport.id).filter(MorningReport.user_id == user_id).first(),
            db.query(RecommendationLog.id).filter(RecommendationLog.user_id == user_id).first(),
        )
    return any(item is not None for item in checks)


@app.get("/api/admin/deleted-members")
def list_deleted_members(
    authorization: str | None = Header(default=None),
):
    """List deletion tombstones without exposing retained portfolio contents."""
    require_admin(authorization)
    with get_db_session() as db:
        tombstones = db.query(DeletedMember).order_by(DeletedMember.deleted_at.desc()).all()

    return {
        "deleted_members": [
            {
                "user_id": str(row.user_id),
                "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None,
                "has_retained_data": _has_retained_member_data(row.user_id),
            }
            for row in tombstones
        ],
        "privacy_scope": "탈퇴 회원의 보존 데이터 내용이나 투자금액은 표시하지 않습니다.",
    }


class MemberAccessRequest(BaseModel):
    active: bool


@app.put("/api/admin/members/{member_id}/access")
def set_member_access(
    member_id: UUID,
    request: MemberAccessRequest,
    authorization: str | None = Header(default=None),
):
    admin = require_admin(authorization)
    if str(member_id) == str(admin["user_id"]) and not request.active:
        raise HTTPException(status_code=400, detail="현재 로그인한 관리자 계정은 중지할 수 없습니다.")
    with get_db_session() as db:
        profile = db.query(Profile).filter(Profile.id == member_id).one_or_none()
        if profile is None:
            raise HTTPException(status_code=404, detail="등록된 회원 정보를 찾을 수 없습니다.")
        if bool(profile.is_admin) and not request.active:
            raise HTTPException(status_code=400, detail="관리자 계정은 회원 관리 화면에서 중지할 수 없습니다.")
        profile.is_active = request.active
        profile.updated_at = datetime.now(timezone.utc)
    return {"user_id": str(member_id), "is_active": request.active}



@app.delete("/api/admin/members/{member_id}")
def delete_member(
    member_id: UUID,
    authorization: str | None = Header(default=None),
):
    admin = require_admin(authorization)
    if str(member_id) == str(admin["user_id"]):
        raise HTTPException(status_code=400, detail="현재 로그인한 관리자 계정은 삭제할 수 없습니다.")
    with get_db_session() as db:
        profile = db.query(Profile).filter(Profile.id == member_id).one_or_none()
        if profile is None:
            raise HTTPException(status_code=404, detail="등록된 회원 정보를 찾을 수 없습니다.")
        if bool(profile.is_admin):
            raise HTTPException(status_code=400, detail="다른 관리자 계정은 여기서 삭제할 수 없습니다.")
    # Fail closed before touching Supabase Auth. If any later deletion step
    # fails, an existing application profile remains unable to use the service.
    with get_db_session() as db:
        profile = db.query(Profile).filter(Profile.id == member_id).one()
        profile.is_active = False
        profile.updated_at = datetime.now(timezone.utc)

    admin_client = _get_supabase_admin_client()
    try:
        admin_client.auth.admin.delete_user(str(member_id))
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="회원 인증 계정을 삭제하지 못했습니다. 계정 접근은 중지된 상태입니다.",
        ) from exc
    # Portfolio rows remain user-scoped and inaccessible. Record a minimal tombstone
    # so a later, explicitly destructive purge can target the exact former user UUID.
    with get_db_session() as db:
        profile = db.query(Profile).filter(Profile.id == member_id).one_or_none()
        if profile is not None:
            db.merge(
                DeletedMember(
                    user_id=member_id,
                    deleted_by=UUID(str(admin["user_id"])),
                    deleted_at=datetime.now(timezone.utc),
                )
            )
            db.delete(profile)
    return {
        "deleted": True,
        "user_id": str(member_id),
        "portfolio_data_deleted": False,
    }


class SignupRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)


@app.post("/api/auth/signup", status_code=201)
def signup(request: SignupRequest):
    """Create a user only while an administrator has enabled registration."""
    if not _signup_enabled():
        raise HTTPException(status_code=403, detail="현재 신규 회원가입이 중지되어 있습니다.")

    supabase_url = os.getenv("SUPABASE_URL", "").strip()
    supabase_anon_key = os.getenv("SUPABASE_ANON_KEY", "").strip()
    supabase_service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not supabase_url or not supabase_anon_key or not supabase_service_key:
        raise HTTPException(status_code=500, detail="Supabase 회원가입 설정이 없습니다.")

    email = request.email.strip().lower()
    admin_client = create_client(supabase_url, supabase_service_key)
    created_user_id: UUID | None = None
    try:
        response = admin_client.auth.admin.create_user({
            "email": email,
            "password": request.password,
            "email_confirm": True,
        })
        if response.user is None:
            raise HTTPException(status_code=400, detail="회원가입을 완료하지 못했습니다.")

        created_user_id = UUID(str(response.user.id))
        try:
            with get_db_session() as db:
                profile = db.query(Profile).filter(Profile.id == created_user_id).one_or_none()
                if profile is None:
                    db.add(Profile(id=created_user_id, is_admin=False, is_active=True))
        except Exception as exc:
            try:
                admin_client.auth.admin.delete_user(str(created_user_id))
            except Exception:
                pass
            raise HTTPException(
                status_code=500,
                detail="회원 정보 저장에 실패하여 생성된 인증 계정을 정리했습니다. 다시 시도해 주세요.",
            ) from exc

        session = None
        try:
            public_client = create_client(supabase_url, supabase_anon_key)
            session_response = public_client.auth.sign_in_with_password({
                "email": email,
                "password": request.password,
            })
            session = session_response.session
        except Exception:
            # Account + Profile creation already succeeded. Auto-login is a
            # convenience step and must not turn a successful signup into a
            # misleading signup failure.
            session = None

        return {
            "created": True,
            "email": response.user.email,
            "email_confirmation_required": False,
            "login_required": session is None,
            "access_token": session.access_token if session else None,
            "refresh_token": session.refresh_token if session else None,
        }
    except HTTPException:
        raise
    except Exception as exc:
        message = str(exc).lower()
        if "already registered" in message or "already been registered" in message or "already exists" in message:
            raise HTTPException(status_code=409, detail="이미 가입된 이메일입니다.")
        raise HTTPException(status_code=400, detail="회원가입을 완료하지 못했습니다.")


@app.post("/api/bootstrap")
def bootstrap_current_user(
    authorization: str | None = Header(default=None),
):
    """로그인 사용자의 필수 기본 레코드를 한 번만 준비합니다."""
    user_id = get_verified_user_id(
        authorization
    )

    try:
        initialized = Repository(
            user_id=user_id
        ).ensure_user_initialized()

        return {
            "initialized": True,
            **initialized,
        }
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="사용자 초기 설정을 준비하지 못했습니다.",
        )


@app.get("/api/reports/latest", response_class=HTMLResponse)
def get_latest_morning_report(
    authorization: str | None = Header(default=None),
):
    """Return the authenticated user's latest trusted server-generated HTML."""
    user_id = get_verified_user_id(authorization)
    report = Repository(user_id=user_id).get_latest_morning_report()
    if report is None:
        raise HTTPException(status_code=404, detail="저장된 모닝 리포트가 없습니다.")
    return HTMLResponse(
        content=report.html_content,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Security-Policy": (
                "default-src 'none'; style-src 'unsafe-inline'; "
                "script-src 'unsafe-inline'; img-src data: https:; "
                "connect-src 'none'; frame-ancestors 'self'; "
                "base-uri 'none'; form-action 'none'"
            ),
        },
    )



def _morning_report_link_serializer() -> URLSafeTimedSerializer:
    secret = os.getenv("OAUTH_TOKEN_ENCRYPTION_KEY", "").strip()
    if not secret:
        raise HTTPException(status_code=500, detail="리포트 링크 보안 키 설정이 없습니다.")
    return URLSafeTimedSerializer(secret, salt="morning-report-link-v1")


@app.get("/report", response_class=HTMLResponse)
def open_signed_morning_report(token: str = ""):
    """Open a user's latest report from a short-lived signed Kakao link."""
    if not token:
        raise HTTPException(status_code=400, detail="상세 리포트 링크 토큰이 없습니다.")
    try:
        data = _morning_report_link_serializer().loads(token, max_age=86400)
    except SignatureExpired:
        raise HTTPException(status_code=410, detail="상세 리포트 링크가 만료되었습니다.")
    except BadSignature:
        raise HTTPException(status_code=403, detail="상세 리포트 링크 서명 검증에 실패했습니다.")

    if data.get("purpose") != "morning-report" or not data.get("user_id"):
        raise HTTPException(status_code=403, detail="상세 리포트 링크 내용이 올바르지 않습니다.")

    try:
        report_user_id = UUID(str(data["user_id"]))
    except (TypeError, ValueError):
        raise HTTPException(status_code=403, detail="상세 리포트 링크 내용이 올바르지 않습니다.")

    with get_db_session() as db:
        profile = db.query(Profile).filter(Profile.id == report_user_id).one_or_none()
        if profile is None or not bool(profile.is_active):
            raise HTTPException(status_code=403, detail="현재 사용할 수 없는 계정의 리포트입니다.")

    report = Repository(user_id=str(report_user_id)).get_latest_morning_report()
    if report is None:
        raise HTTPException(status_code=404, detail="저장된 모닝 리포트가 없습니다.")

    return HTMLResponse(
        content=report.html_content,
        headers={
            "Cache-Control": "private, no-store",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": (
                "default-src 'none'; style-src 'unsafe-inline'; "
                "script-src 'unsafe-inline'; img-src data: https:; "
                "connect-src 'none'; frame-ancestors 'none'; "
                "base-uri 'none'; form-action 'none'"
            ),
        },
    )

# =========================================================
# Kakao OAuth connection
# =========================================================

def _kakao_state_serializer() -> URLSafeTimedSerializer:
    secret = os.getenv("OAUTH_TOKEN_ENCRYPTION_KEY", "").strip()
    if not secret:
        raise HTTPException(status_code=500, detail="OAuth 보안 키 설정이 없습니다.")
    return URLSafeTimedSerializer(secret, salt="kakao-oauth-state-v1")


def _kakao_redirect_uri() -> str:
    base = os.getenv("RETIREMENT_PORTFOLIO_WEB_URL", "").strip().rstrip("/")
    if not base:
        raise HTTPException(status_code=500, detail="웹 앱 공개 URL 설정이 없습니다.")
    return f"{base}/api/kakao/callback"


@app.get("/api/kakao/connect")
def connect_kakao(authorization: str | None = Header(default=None)):
    """Return a Kakao authorization URL; the user never handles OAuth tokens."""
    user_id = get_verified_user_id(authorization)
    client_id = os.getenv("KAKAO_REST_API_KEY", "").strip()
    if not client_id:
        raise HTTPException(status_code=500, detail="Kakao REST API 설정이 없습니다.")

    state = _kakao_state_serializer().dumps({
        "user_id": user_id,
        "purpose": "kakao-connect",
    })
    params = urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": _kakao_redirect_uri(),
        "response_type": "code",
        "scope": "talk_message",
        "state": state,
    })
    return {"authorization_url": f"https://kauth.kakao.com/oauth/authorize?{params}"}


@app.get("/api/kakao/callback")
def kakao_callback(code: str = "", state: str = "", error: str = ""):
    """Exchange the one-time authorization code and store encrypted user tokens."""
    if error or not code or not state:
        raise HTTPException(status_code=400, detail="카카오 연결 요청이 취소되었거나 올바르지 않습니다.")
    try:
        state_data = _kakao_state_serializer().loads(state, max_age=600)
    except (BadSignature, SignatureExpired):
        raise HTTPException(status_code=400, detail="카카오 연결 요청이 만료되었거나 유효하지 않습니다.")
    if state_data.get("purpose") != "kakao-connect" or not state_data.get("user_id"):
        raise HTTPException(status_code=400, detail="유효하지 않은 카카오 연결 요청입니다.")

    user_id = state_data["user_id"]
    try:
        member_id = UUID(str(user_id))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="유효하지 않은 카카오 연결 요청입니다.")

    with get_db_session() as db:
        profile = db.query(Profile).filter(Profile.id == member_id).one_or_none()
        if profile is None or not bool(profile.is_active):
            raise HTTPException(
                status_code=403,
                detail="현재 이용 가능한 회원 계정이 아닙니다.",
            )

    client_id = os.getenv("KAKAO_REST_API_KEY", "").strip()
    client_secret = os.getenv("KAKAO_CLIENT_SECRET", "").strip()
    form = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "redirect_uri": _kakao_redirect_uri(),
        "code": code,
    }
    if client_secret:
        form["client_secret"] = client_secret

    request = urllib.request.Request(
        "https://kauth.kakao.com/oauth/token",
        data=urllib.parse.urlencode(form).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            token_data = json.loads(response.read().decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=502, detail="카카오 토큰 발급에 실패했습니다.")

    access_token = token_data.get("access_token", "")
    refresh_token = token_data.get("refresh_token", "")
    if not access_token or not refresh_token:
        raise HTTPException(status_code=502, detail="카카오 토큰 응답이 올바르지 않습니다.")

    granted_scopes = {
        scope.strip()
        for scope in str(token_data.get("scope", "")).split()
        if scope.strip()
    }
    if "talk_message" not in granted_scopes:
        raise HTTPException(
            status_code=403,
            detail=(
                "카카오톡 메시지 전송 권한(talk_message)에 동의되지 않았습니다. "
                "카카오 개발자 앱의 카카오 로그인 > 동의항목에서 "
                "'카카오톡 메시지 전송'을 사용 가능하게 설정한 뒤 다시 연결해주세요."
            ),
        )

    now = datetime.now(timezone.utc)
    Repository(user_id=user_id).save_kakao_credential(
        access_token_encrypted=encrypt_secret(access_token),
        refresh_token_encrypted=encrypt_secret(refresh_token),
        access_token_expires_at=now + timedelta(seconds=int(token_data.get("expires_in", 0) or 0)),
        refresh_token_expires_at=now + timedelta(seconds=int(token_data.get("refresh_token_expires_in", 0) or 0)),
        scopes=" ".join(sorted(granted_scopes)),
    )
    settings = Repository(user_id=user_id).get_user_settings()
    if settings is not None and not settings.kakao_enabled:
        Repository(user_id=user_id).save_user_settings(
            morning_report_enabled=settings.morning_report_enabled,
            morning_report_time=settings.morning_report_time.strftime("%H:%M"),
            kakao_enabled=True,
            news_enabled=settings.news_enabled,
            ai_advice_enabled=settings.ai_advice_enabled,
        )
    return RedirectResponse(url="/?kakao=connected", status_code=303)


@app.get("/api/kakao/status")
def kakao_status(authorization: str | None = Header(default=None)):
    user_id = get_verified_user_id(authorization)
    credential = Repository(user_id=user_id).get_kakao_credential()
    granted_scopes = {
        scope.strip()
        for scope in str(getattr(credential, "scopes", "") or "").split()
        if scope.strip()
    }
    connected = credential is not None and "talk_message" in granted_scopes
    return {
        "connected": connected,
        "needs_reconnect": credential is not None and not connected,
    }


@app.post("/api/kakao/test")
def kakao_test_message(authorization: str | None = Header(default=None)):
    """Send an immediate test message using only the authenticated user's Kakao token."""
    user_id = get_verified_user_id(authorization)
    repo = Repository(user_id=user_id)
    service = KakaoService.for_user(__import__("core.config", fromlist=["load_config"]).load_config(), repo)
    if not service.is_configured():
        raise HTTPException(status_code=400, detail="먼저 카카오톡 계정을 연결해 주세요.")
    web_url = os.getenv("RETIREMENT_PORTFOLIO_WEB_URL", "").strip()
    ok, message = service.send_test_message(web_url=web_url)
    if not ok:
        raise HTTPException(status_code=502, detail=f"카카오톡 테스트 발송에 실패했습니다: {message}")
    return {"sent": True, "message": "카카오톡 테스트 메시지를 보냈습니다."}


@app.delete("/api/kakao/disconnect")
def kakao_disconnect(authorization: str | None = Header(default=None)):
    """Remove this user's Kakao OAuth credential and disable Kakao delivery."""
    user_id = get_verified_user_id(authorization)
    repo = Repository(user_id=user_id)
    repo.delete_kakao_credential()
    settings = repo.get_user_settings()
    if settings is not None:
        repo.save_user_settings(
            morning_report_enabled=settings.morning_report_enabled,
            morning_report_time=settings.morning_report_time.strftime("%H:%M"),
            kakao_enabled=False,
            news_enabled=settings.news_enabled,
            ai_advice_enabled=settings.ai_advice_enabled,
        )
    return {"connected": False}


# =========================================================
# Request Models
# =========================================================

class MorningReportSettingsRequest(BaseModel):
    morning_report_enabled: bool = True
    morning_report_time: str = Field(default="07:30", min_length=5, max_length=5)
    news_enabled: bool = True
    ai_advice_enabled: bool = True


@app.get("/api/morning-report/settings")
def get_morning_report_settings(authorization: str | None = Header(default=None)):
    user_id = get_verified_user_id(authorization)
    repo = Repository(user_id=user_id)
    settings = repo.get_user_settings()
    if settings is None:
        repo.ensure_user_initialized()
        settings = repo.get_user_settings()
    return {
        "morning_report_enabled": bool(settings.morning_report_enabled),
        "morning_report_time": settings.morning_report_time.strftime("%H:%M"),
        "kakao_enabled": bool(settings.kakao_enabled),
        "news_enabled": bool(settings.news_enabled),
        "ai_advice_enabled": bool(settings.ai_advice_enabled),
    }


@app.put("/api/morning-report/settings")
def update_morning_report_settings(
    payload: MorningReportSettingsRequest,
    authorization: str | None = Header(default=None),
):
    user_id = get_verified_user_id(authorization)
    repo = Repository(user_id=user_id)
    current = repo.get_user_settings()
    kakao_enabled = bool(current.kakao_enabled) if current is not None else False
    saved = repo.save_user_settings(
        morning_report_enabled=payload.morning_report_enabled,
        morning_report_time=payload.morning_report_time,
        kakao_enabled=kakao_enabled,
        news_enabled=payload.news_enabled,
        ai_advice_enabled=payload.ai_advice_enabled,
    )
    return {
        "morning_report_enabled": bool(saved.morning_report_enabled),
        "morning_report_time": saved.morning_report_time.strftime("%H:%M"),
        "kakao_enabled": bool(saved.kakao_enabled),
        "news_enabled": bool(saved.news_enabled),
        "ai_advice_enabled": bool(saved.ai_advice_enabled),
    }


class AccountUpdateRequest(BaseModel):
    """계좌별 운용 및 자금 설정 수정 요청."""

    account_name: str = Field(
        min_length=1,
        max_length=200,
    )

    account_number: str = Field(
        default="",
        max_length=200,
    )

    broker: str = Field(
        default="",
        max_length=200,
    )

    initial_capital: float = Field(
        default=0,
        ge=0,
    )

    base_monthly: float = Field(
        default=0,
        ge=0,
    )

    max_additional_monthly: float = Field(
        default=0,
        ge=0,
    )

    buy_cycle_type: str = Field(
        default="monthly",
        max_length=50,
    )

    buy_cycle_detail: str = Field(
        default="25",
        max_length=100,
    )

    currency: str = Field(
        default="KRW",
        max_length=10,
    )

    account_type: str = Field(
        default="brokerage",
        max_length=50,
    )

    market_scope: str = Field(
        default="KR",
        max_length=20,
    )

    contribution_type: str = Field(
        default="none",
        max_length=50,
    )

    contribution_amount: float = Field(
        default=0,
        ge=0,
    )

    contribution_month: int | None = Field(
        default=None,
        ge=1,
        le=12,
    )

    strategy_type: str = Field(
        default="allocation",
        max_length=50,
    )

    is_default: bool = False

    memo: str = Field(
        default="",
        max_length=2000,
    )


class InvestmentProfileRequest(BaseModel):
    """사용자 투자 성향 및 AI 투자전략 설정."""

    risk_profile: str = Field(
        default="balanced",
        max_length=50,
    )

    investment_horizon_years: int | None = Field(
        default=None,
        ge=0,
        le=100,
    )

    target_return: float | None = None
    max_drawdown: float | None = None

    # 기존 DB 호환성을 위해 유지합니다.
    # 실제 계좌별 투자금은 accounts에서 관리합니다.
    monthly_investment: float = Field(
        default=0,
        ge=0,
    )

    preferred_markets: list[str] = Field(
        default_factory=list,
    )

    excluded_assets: list[str] = Field(
        default_factory=list,
    )

    ai_advice_enabled: bool = True

    ai_advice_style: str = Field(
        default="balanced",
        max_length=50,
    )

    memo: str = Field(
        default="",
        max_length=2000,
    )

    investment_preference_text: str = Field(
        default="",
        max_length=10000,
    )


class TransactionCreateRequest(BaseModel):
    """매수/매도 거래 등록 및 수정 요청."""

    transaction_date: date

    ticker: str = Field(
        min_length=1,
        max_length=30,
    )

    transaction_type: str = Field(
        min_length=3,
        max_length=4,
    )

    quantity: float = Field(gt=0)
    price: float = Field(gt=0)
    fee: float = Field(default=0, ge=0)
    tax: float = Field(default=0, ge=0)

    memo: str = Field(
        default="",
        max_length=1000,
    )

class CashFlowRequest(BaseModel):
    flow_date: date
    flow_type: str = Field(min_length=7, max_length=10)
    amount: float = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    memo: str = Field(default="", max_length=1000)
    
# =========================================================
# 계좌 API
# =========================================================

def account_to_dict(account):
    """Account 모델을 웹 API 형식으로 변환합니다."""

    return {
        "id": account.id,
        "account_name": account.account_name,
        "account_number": account.account_number or "",
        "broker": account.broker or "",

        "initial_capital":
            float(account.initial_capital or 0),

        "base_monthly":
            float(account.base_monthly or 0),

        "max_additional_monthly":
            float(account.max_additional_monthly or 0),

        "buy_cycle_type":
            account.buy_cycle_type or "monthly",

        "buy_cycle_detail":
            account.buy_cycle_detail or "25",

        "currency":
            account.currency or "KRW",

        "account_type":
            account.account_type or "brokerage",

        "market_scope":
            account.market_scope or "KR",

        "contribution_type":
            account.contribution_type or "none",

        "contribution_amount":
            float(account.contribution_amount or 0),

        "contribution_month":
            account.contribution_month,

        "strategy_type":
            account.strategy_type or "allocation",

        "is_default":
            bool(account.is_default),

        "memo":
            account.memo or "",
    }


@app.post(
    "/api/accounts",
    status_code=201,
)
def create_account_api(
    request: AccountUpdateRequest,
    authorization: str | None = Header(default=None),
):
    """
    로그인한 사용자의 신규 계좌를 생성합니다.

    계좌만 생성하며 기존 계좌의 목표 종목이나
    거래내역은 복사하지 않습니다.
    """

    user_id = get_verified_user_id(
        authorization
    )

    try:
        repo = Repository(
            user_id=user_id
        )

        account = repo.create_account(
            account_name=
                request.account_name,

            account_number=
                request.account_number,

            broker=
                request.broker,

            initial_capital=
                request.initial_capital,

            base_monthly=
                request.base_monthly,

            max_additional_monthly=
                request.max_additional_monthly,

            buy_cycle_type=
                request.buy_cycle_type,

            buy_cycle_detail=
                request.buy_cycle_detail,

            currency=
                request.currency,

            account_type=
                request.account_type,

            market_scope=
                request.market_scope,

            contribution_type=
                request.contribution_type,

            contribution_amount=
                request.contribution_amount,

            contribution_month=
                request.contribution_month,

            strategy_type=
                request.strategy_type,

            is_default=
                int(request.is_default),

            memo=
                request.memo,
        )

        return {
            "created": True,
            "account":
                account_to_dict(
                    account
                ),
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="계좌를 생성하지 못했습니다.",
        )
        

@app.get("/api/accounts")
def get_accounts_api(
    authorization: str | None = Header(default=None),
):
    user_id = get_verified_user_id(
        authorization
    )

    try:
        repo = Repository(
            user_id=user_id
        )

        accounts = repo.get_accounts()

        return {
            "accounts": [
                account_to_dict(account)
                for account in accounts
            ]
        }

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="계좌 정보를 불러오지 못했습니다.",
        )


@app.put("/api/accounts/{account_id}")
def update_account_api(
    account_id: int,
    request: AccountUpdateRequest,
    authorization: str | None = Header(default=None),
):
    """로그인 사용자의 계좌 설정을 수정합니다."""

    user_id = get_verified_user_id(
        authorization
    )

    try:
        repo = Repository(
            user_id=user_id
        )

        account = repo.get_account(
            account_id
        )

        if account is None:
            raise HTTPException(
                status_code=404,
                detail="계좌를 찾을 수 없습니다.",
            )

        updated = repo.update_account(
            account_id=account_id,
            account_name=request.account_name,
            account_number=request.account_number,
            broker=request.broker,
            initial_capital=request.initial_capital,
            base_monthly=request.base_monthly,
            max_additional_monthly=
                request.max_additional_monthly,
            buy_cycle_type=request.buy_cycle_type,
            buy_cycle_detail=request.buy_cycle_detail,
            currency=request.currency,
            account_type=request.account_type,
            market_scope=request.market_scope,
            contribution_type=
                request.contribution_type,
            contribution_amount=
                request.contribution_amount,
            contribution_month=
                request.contribution_month,
            strategy_type=request.strategy_type,
            is_default=int(request.is_default),
            memo=request.memo,
        )

        if not updated:
            raise HTTPException(
                status_code=404,
                detail="계좌를 찾을 수 없습니다.",
            )

        saved_account = repo.get_account(
            account_id
        )

        if saved_account is None:
            raise HTTPException(
                status_code=404,
                detail="계좌를 찾을 수 없습니다.",
            )

        return {
            "updated": True,
            "account":
                account_to_dict(saved_account),
        }

    except HTTPException:
        raise

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="계좌 설정을 저장하지 못했습니다.",
        )

@app.delete(
    "/api/accounts/{account_id}"
)
def delete_account_api(
    account_id: int,
    authorization: str | None = Header(default=None),
):
    """
    로그인한 사용자의 계좌를 삭제합니다.

    다른 사용자의 계좌는 삭제할 수 없습니다.
    """

    user_id = get_verified_user_id(
        authorization
    )

    try:
        repo = Repository(
            user_id=user_id
        )

        account = repo.get_account(
            account_id
        )

        if account is None:
            raise HTTPException(
                status_code=404,
                detail="계좌를 찾을 수 없습니다.",
            )

        account_name = (
            account.account_name
        )

        deleted = repo.delete_account(
            account_id
        )

        if not deleted:
            raise HTTPException(
                status_code=404,
                detail="계좌를 찾을 수 없습니다.",
            )

        return {
            "deleted": True,
            "account_id":
                account_id,
            "account_name":
                account_name,
        }

    except HTTPException:
        raise

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="계좌를 삭제하지 못했습니다.",
        )


# =========================================================
# 목표 포트폴리오
# =========================================================

@app.get(
    "/api/accounts/{account_id}/targets"
)
def get_account_targets_api(
    account_id: int,
    authorization: str | None = Header(default=None),
):
    user_id = get_verified_user_id(
        authorization
    )

    try:
        repo = Repository(
            user_id=user_id
        )

        account = repo.get_account(
            account_id
        )

        if account is None:
            raise HTTPException(
                status_code=404,
                detail="계좌를 찾을 수 없습니다.",
            )

        targets = repo.get_account_targets(
            account_id=account_id
        )

        return {
            "account_id": account.id,
            "account_name":
                account.account_name,

            "targets": [
                {
                    "ticker":
                        target.ticker,

                    "name":
                        target.name,

                    "target_weight":
                        float(
                            target.target_weight
                            or 0
                        ),

                    "dividend_yield":
                        float(
                            target.dividend_yield
                            or 0
                        ),
                }
                for target in targets
            ],
        }

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="목표 투자 비중을 불러오지 못했습니다.",
        )


# =========================================================
# 투자성향 API
# =========================================================

@app.get("/api/investment-profile")
def get_investment_profile_api(
    authorization: str | None = Header(default=None),
):
    user_id = get_verified_user_id(
        authorization
    )

    try:
        repo = Repository(
            user_id=user_id
        )

        profile = repo.get_investment_profile()

        if profile is None:
            return {
                "profile": None,
            }

        return {
            "profile": {
                "risk_profile":
                    profile.risk_profile,

                "investment_horizon_years":
                    profile.investment_horizon_years,

                "target_return":
                    (
                        float(profile.target_return)
                        if profile.target_return
                        is not None
                        else None
                    ),

                "max_drawdown":
                    (
                        float(profile.max_drawdown)
                        if profile.max_drawdown
                        is not None
                        else None
                    ),

                "monthly_investment":
                    float(
                        profile.monthly_investment
                        or 0
                    ),

                "preferred_markets":
                    profile.preferred_markets
                    or [],

                "excluded_assets":
                    profile.excluded_assets
                    or [],

                "ai_advice_enabled":
                    bool(
                        profile.ai_advice_enabled
                    ),

                "ai_advice_style":
                    profile.ai_advice_style,

                "memo":
                    profile.memo or "",

                "investment_preference_text":
                    (
                        profile
                        .investment_preference_text
                        or ""
                    ),
            }
        }

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="투자 성향을 불러오지 못했습니다.",
        )


@app.put("/api/investment-profile")
def update_investment_profile_api(
    request: InvestmentProfileRequest,
    authorization: str | None = Header(default=None),
):
    user_id = get_verified_user_id(
        authorization
    )

    try:
        repo = Repository(
            user_id=user_id
        )

        profile = repo.save_investment_profile(
            risk_profile=
                request.risk_profile,

            investment_horizon_years=
                request.investment_horizon_years,

            target_return=
                request.target_return,

            max_drawdown=
                request.max_drawdown,

            monthly_investment=
                request.monthly_investment,

            preferred_markets=
                request.preferred_markets,

            excluded_assets=
                request.excluded_assets,

            ai_advice_enabled=
                request.ai_advice_enabled,

            ai_advice_style=
                request.ai_advice_style,

            memo=
                request.memo,

            investment_preference_text=
                request.investment_preference_text,
        )

        return {
            "saved": True,

            "profile": {
                "risk_profile":
                    profile.risk_profile,

                "investment_horizon_years":
                    profile.investment_horizon_years,

                "target_return":
                    (
                        float(profile.target_return)
                        if profile.target_return
                        is not None
                        else None
                    ),

                "max_drawdown":
                    (
                        float(profile.max_drawdown)
                        if profile.max_drawdown
                        is not None
                        else None
                    ),

                "monthly_investment":
                    float(
                        profile.monthly_investment
                        or 0
                    ),

                "preferred_markets":
                    profile.preferred_markets
                    or [],

                "excluded_assets":
                    profile.excluded_assets
                    or [],

                "ai_advice_enabled":
                    bool(
                        profile.ai_advice_enabled
                    ),

                "ai_advice_style":
                    profile.ai_advice_style,

                "memo":
                    profile.memo or "",

                "investment_preference_text":
                    (
                        profile
                        .investment_preference_text
                        or ""
                    ),
            },
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="투자 성향을 저장하지 못했습니다.",
        )


# =========================================================
# 미국 종목 검색 API
# =========================================================

@app.get("/api/assets/us/{ticker}")
def lookup_us_asset_api(
    ticker: str,
    authorization: str | None = Header(default=None),
):
    """
    미국 주식/ETF ticker를 Yahoo Finance에서 조회합니다.

    이 API는 조회만 수행하며
    asset_master나 거래내역에는 저장하지 않습니다.
    """

    # 로그인 사용자만 종목 검색 API를 사용할 수 있습니다.
    get_verified_user_id(
        authorization
    )

    clean_ticker = (
        str(ticker or "")
        .strip()
        .upper()
    )

    if not clean_ticker:
        raise HTTPException(
            status_code=400,
            detail="미국 종목 ticker를 입력해주세요.",
        )

    if len(clean_ticker) > 30:
        raise HTTPException(
            status_code=400,
            detail="ticker가 너무 깁니다.",
        )

    try:
        client = YFinanceClient()

        asset = client.fetch_asset_info(
            clean_ticker
        )

        return {
            "found": True,
            "asset": {
                "ticker":
                    asset["ticker"],

                "name":
                    asset["name"],

                "market":
                    asset["market"],

                "exchange":
                    asset["exchange"],

                "asset_type":
                    asset["asset_type"],

                "currency":
                    asset["currency"],
            },
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        )

    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )

    except Exception:
        raise HTTPException(
            status_code=502,
            detail=(
                "미국 종목 정보를 "
                "조회하지 못했습니다."
            ),
        )

@app.post(
    "/api/assets/us/{ticker}/register",
    status_code=201,
)
def register_us_asset_api(
    ticker: str,
    authorization: str | None = Header(default=None),
):
    """
    미국 주식/ETF를 Yahoo Finance에서 확인한 뒤
    asset_master에 등록하거나 최신 정보로 갱신합니다.

    사용자가 입력한 이름/시장/통화를 그대로 신뢰하지 않고
    서버가 Yahoo Finance에서 다시 확인합니다.
    """

    user_id = get_verified_user_id(
        authorization
    )

    clean_ticker = (
        str(ticker or "")
        .strip()
        .upper()
    )

    if not clean_ticker:
        raise HTTPException(
            status_code=400,
            detail="미국 종목 ticker를 입력해주세요.",
        )

    if len(clean_ticker) > 30:
        raise HTTPException(
            status_code=400,
            detail="ticker가 너무 깁니다.",
        )

    try:
        # 브라우저에서 전달받은 종목정보를
        # 그대로 저장하지 않고 서버에서 다시 확인합니다.
        client = YFinanceClient()

        asset = client.fetch_asset_info(
            clean_ticker
        )

        repo = Repository(
            user_id=user_id
        )

        saved_count = repo.save_etf_master(
            [
                {
                    "ticker":
                        asset["ticker"],

                    "name":
                        asset["name"],

                    "market":
                        asset["market"],

                    "exchange":
                        asset["exchange"],

                    "asset_type":
                        asset["asset_type"],

                    "currency":
                        asset["currency"],
                }
            ]
        )

        if saved_count != 1:
            raise RuntimeError(
                "자산 마스터 저장 결과가 올바르지 않습니다."
            )

        saved_asset = repo.get_etf_master(
            asset["ticker"]
        )

        if saved_asset is None:
            raise RuntimeError(
                "저장한 종목을 다시 확인하지 못했습니다."
            )

        return {
            "registered": True,

            "asset": {
                "ticker":
                    saved_asset.ticker,

                "name":
                    saved_asset.name,

                "market":
                    saved_asset.market,

                "exchange":
                    saved_asset.exchange,

                "asset_type":
                    saved_asset.asset_type,

                "currency":
                    saved_asset.currency,
            },
        }

    except HTTPException:
        raise

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        )

    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="미국 종목을 등록하지 못했습니다.",
        )

# =========================================================
# 등록 자산 검색 API
# =========================================================

@app.get("/api/assets")
def search_assets_api(
    q: str = "",
    limit: int = 50,
    authorization: str | None = Header(default=None),
):
    """
    asset_master에 등록된 활성 자산을 검색합니다.

    종목코드 또는 종목명으로 검색할 수 있으며
    한국/미국 자산을 모두 반환합니다.
    """

    user_id = get_verified_user_id(
        authorization
    )

    clean_keyword = (
        str(q or "")
        .strip()
    )

    safe_limit = max(
        1,
        min(
            int(limit),
            100,
        ),
    )

    try:
        repo = Repository(
            user_id=user_id
        )

        assets = repo.search_etf_master(
            keyword=clean_keyword,
            limit=safe_limit,
        )

        return {
            "query":
                clean_keyword,

            "count":
                len(assets),

            "assets":
                assets,
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="등록된 종목을 검색하지 못했습니다.",
        )


@app.get(
    "/api/accounts/{account_id}/assets/{ticker}/chart"
)
def get_asset_chart_api(
    account_id: int,
    ticker: str,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int | None = None,
    authorization: str | None = Header(default=None),
):
    """
    현재 사용자의 특정 계좌/종목에 대한
    가격 차트와 실제 매수/매도 내역을 반환합니다.

    선택 파라미터:
    - start_date: YYYYMMDD 또는 YYYY-MM-DD
    - end_date: YYYYMMDD 또는 YYYY-MM-DD
    - limit: 최신 가격 N개
    """

    user_id = get_verified_user_id(
        authorization
    )

    try:
        repo = Repository(
            user_id=user_id
        )

        # -----------------------------------------------------
        # 1. 현재 사용자가 소유한 계좌인지 확인
        # -----------------------------------------------------

        account = repo.get_account(
            account_id
        )

        if account is None:
            raise HTTPException(
                status_code=404,
                detail="계좌를 찾을 수 없습니다.",
            )


        # -----------------------------------------------------
        # 2. 종목코드 정규화
        # -----------------------------------------------------

        clean_ticker = (
            str(
                ticker or ""
            )
            .strip()
            .upper()
        )

        if not clean_ticker:
            raise HTTPException(
                status_code=400,
                detail="종목코드가 필요합니다.",
            )


        # -----------------------------------------------------
        # 3. limit 검증
        # -----------------------------------------------------

        if (
            limit is not None
            and limit <= 0
        ):
            raise HTTPException(
                status_code=400,
                detail="limit은 1 이상이어야 합니다.",
            )


        # -----------------------------------------------------
        # 4. 해당 계좌에 실제 거래가 있는 종목인지 확인
        #
        # 다른 계좌의 종목을 임의로 조회하는 것을 막고
        # 현재 단계에서는 보유/거래 종목 차트만 제공합니다.
        # -----------------------------------------------------

        transactions = (
            repo.get_transactions(
                ticker=clean_ticker,
                account_id=account_id,
            )
        )

        if not transactions:
            raise HTTPException(
                status_code=404,
                detail=(
                    "해당 계좌에서 이 종목의 "
                    "거래 내역을 찾을 수 없습니다."
                ),
            )


        # -----------------------------------------------------
        # 5. 가격 + 매수/매도 데이터 조회
        # -----------------------------------------------------

        chart_data = (
            repo.get_asset_chart_data(
                account_id=account_id,
                ticker=clean_ticker,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
            )
        )


        # -----------------------------------------------------
        # 6. 가격 데이터 확인
        # -----------------------------------------------------

        prices = (
            chart_data.get(
                "prices",
                [],
            )
            or []
        )

        chart_transactions = (
            chart_data.get(
                "transactions",
                [],
            )
            or []
        )


        # -----------------------------------------------------
        # 7. 웹 응답
        # -----------------------------------------------------

        return {
            "account_id":
                account.id,

            "account_name":
                account.account_name,

            "account_currency":
                str(
                    account.currency
                    or "KRW"
                )
                .strip()
                .upper(),

            "ticker":
                chart_data.get(
                    "ticker",
                    clean_ticker,
                ),

            "name":
                chart_data.get(
                    "name",
                    clean_ticker,
                ),

            # 차트 가격과 거래 체결가격의 통화
            "currency":
                chart_data.get(
                    "currency",
                    account.currency
                    or "KRW",
                ),

            "market":
                chart_data.get(
                    "market",
                    "",
                ),

            "price_count":
                len(
                    prices
                ),

            "transaction_count":
                len(
                    chart_transactions
                ),

            "prices":
                prices,

            "transactions":
                chart_transactions,
        }

    except HTTPException:
        raise

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="차트 데이터를 불러오지 못했습니다.",
        )
        
# =========================================================
# 거래 API
# =========================================================

@app.get(
    "/api/accounts/{account_id}/transactions"
)
def get_transactions_api(
    account_id: int,
    authorization: str | None = Header(default=None),
):
    user_id = get_verified_user_id(
        authorization
    )

    try:
        repo = Repository(
            user_id=user_id
        )

        account = repo.get_account(
            account_id
        )

        if account is None:
            raise HTTPException(
                status_code=404,
                detail="계좌를 찾을 수 없습니다.",
            )

        transactions = repo.get_transactions(
            account_id=account_id
        )

        transaction_items = []

        for transaction in transactions:

            asset = repo.get_etf_master(
                transaction.ticker
            )

            if asset is not None:
                asset_name = (
                    asset.name
                    or transaction.ticker
                )

                asset_currency = (
                    str(
                        asset.currency
                        or account.currency
                        or "KRW"
                    )
                    .strip()
                    .upper()
                )

                asset_market = (
                    asset.market
                    or ""
                )

            else:
                asset_name = (
                    transaction.ticker
                )

                asset_currency = (
                    str(
                        account.currency
                        or "KRW"
                    )
                    .strip()
                    .upper()
                )

                asset_market = ""

            transaction_items.append(
                {
                    "id":
                        transaction.id,

                    "transaction_date":
                        transaction
                        .transaction_date
                        .isoformat(),

                    "ticker":
                        transaction.ticker,

                    "name":
                        asset_name,

                    "currency":
                        asset_currency,

                    "market":
                        asset_market,

                    "transaction_type":
                        transaction.transaction_type,

                    "quantity":
                        float(
                            transaction.quantity
                            or 0
                        ),

                    "price":
                        float(
                            transaction.price
                            or 0
                        ),

                    "fee":
                        float(
                            transaction.fee
                            or 0
                        ),

                    "tax":
                        float(
                            transaction.tax
                            or 0
                        ),

                    "memo":
                        transaction.memo
                        or "",
                }
            )

        return {
            "account_id":
                account.id,

            "account_name":
                account.account_name,

            "account_currency":
                str(
                    account.currency
                    or "KRW"
                ).upper(),

            "transactions":
                transaction_items,
        }

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="거래 내역을 불러오지 못했습니다.",
        )

@app.post(
    "/api/accounts/{account_id}/transactions",
    status_code=201,
)
def create_transaction_api(
    account_id: int,
    request: TransactionCreateRequest,
    authorization: str | None = Header(default=None),
):
    user_id = get_verified_user_id(
        authorization
    )

    try:
        repo = Repository(
            user_id=user_id
        )

        account = repo.get_account(
            account_id
        )

        if account is None:
            raise HTTPException(
                status_code=404,
                detail="계좌를 찾을 수 없습니다.",
            )

        transaction = repo.add_transaction(
            transaction_date=
                request.transaction_date,

            ticker=
                request.ticker,

            transaction_type=
                request.transaction_type,

            quantity=
                request.quantity,

            price=
                request.price,

            fee=
                request.fee,

            tax=
                request.tax,

            memo=
                request.memo,

            account_id=
                account_id,
        )

        return {
            "created": True,

            "transaction": {
                "id":
                    transaction.id,

                "account_id":
                    transaction.account_id,

                "transaction_date":
                    transaction
                    .transaction_date
                    .isoformat(),

                "ticker":
                    transaction.ticker,

                "transaction_type":
                    transaction.transaction_type,

                "quantity":
                    float(
                        transaction.quantity
                        or 0
                    ),

                "price":
                    float(
                        transaction.price
                        or 0
                    ),

                "fee":
                    float(
                        transaction.fee
                        or 0
                    ),

                "tax":
                    float(
                        transaction.tax
                        or 0
                    ),

                "memo":
                    transaction.memo
                    or "",
            },
        }

    except HTTPException:
        raise

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="거래를 저장하지 못했습니다.",
        )


@app.put(
    "/api/accounts/{account_id}/transactions/{tx_id}"
)
def update_transaction_api(
    account_id: int,
    tx_id: int,
    request: TransactionCreateRequest,
    authorization: str | None = Header(default=None),
):
    user_id = get_verified_user_id(
        authorization
    )

    try:
        repo = Repository(
            user_id=user_id
        )

        account = repo.get_account(
            account_id
        )

        if account is None:
            raise HTTPException(
                status_code=404,
                detail="계좌를 찾을 수 없습니다.",
            )

        transactions = repo.get_transactions(
            account_id=account_id
        )

        transaction_exists = any(
            transaction.id == tx_id
            for transaction in transactions
        )

        if not transaction_exists:
            raise HTTPException(
                status_code=404,
                detail="거래 내역을 찾을 수 없습니다.",
            )

        updated = repo.update_transaction(
            tx_id=tx_id,

            transaction_date=
                request.transaction_date,

            ticker=
                request.ticker,

            transaction_type=
                request.transaction_type,

            quantity=
                request.quantity,

            price=
                request.price,

            fee=
                request.fee,

            tax=
                request.tax,

            memo=
                request.memo,

            account_id=
                account_id,
        )

        if not updated:
            raise HTTPException(
                status_code=404,
                detail="거래 내역을 찾을 수 없습니다.",
            )

        return {
            "updated": True,
            "transaction_id": tx_id,
        }

    except HTTPException:
        raise

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="거래 내역을 수정하지 못했습니다.",
        )


@app.delete(
    "/api/accounts/{account_id}/transactions/{tx_id}"
)
def delete_transaction_api(
    account_id: int,
    tx_id: int,
    authorization: str | None = Header(default=None),
):
    user_id = get_verified_user_id(
        authorization
    )

    try:
        repo = Repository(
            user_id=user_id
        )

        account = repo.get_account(
            account_id
        )

        if account is None:
            raise HTTPException(
                status_code=404,
                detail="계좌를 찾을 수 없습니다.",
            )

        transactions = repo.get_transactions(
            account_id=account_id
        )

        transaction_exists = any(
            transaction.id == tx_id
            for transaction in transactions
        )

        if not transaction_exists:
            raise HTTPException(
                status_code=404,
                detail="거래 내역을 찾을 수 없습니다.",
            )

        deleted = repo.delete_transaction(
            tx_id=tx_id
        )

        if not deleted:
            raise HTTPException(
                status_code=404,
                detail="거래 내역을 찾을 수 없습니다.",
            )

        return {
            "deleted": True,
            "transaction_id": tx_id,
        }

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="거래 내역을 삭제하지 못했습니다.",
        )

# =========================================================
# 현금 입출금 API
# =========================================================

@app.get(
    "/api/accounts/{account_id}/cash-flows"
)
def get_cash_flows_api(
    account_id: int,
    authorization: str | None = Header(default=None),
):
    user_id = get_verified_user_id(
        authorization
    )

    try:
        repo = Repository(
            user_id=user_id
        )

        account = repo.get_account(
            account_id
        )

        if account is None:
            raise HTTPException(
                status_code=404,
                detail="계좌를 찾을 수 없습니다.",
            )

        cash_flows = repo.get_cash_flows(
            account_id
        )

        cash_flow_items = []

        for cash_flow in cash_flows:
            cash_flow_items.append(
                {
                    "id":
                        cash_flow.id,

                    "account_id":
                        cash_flow.account_id,

                    "flow_date":
                        cash_flow
                        .flow_date
                        .isoformat(),

                    "flow_type":
                        cash_flow.flow_type,

                    "amount":
                        float(
                            cash_flow.amount
                            or 0
                        ),

                    "currency":
                        str(
                            cash_flow.currency
                            or account.currency
                            or "KRW"
                        )
                        .strip()
                        .upper(),

                    "memo":
                        cash_flow.memo
                        or "",
                }
            )

        return {
            "account_id":
                account.id,

            "account_name":
                account.account_name,

            "account_currency":
                str(
                    account.currency
                    or "KRW"
                )
                .strip()
                .upper(),

            "cash_flows":
                cash_flow_items,
        }

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="입출금 내역을 불러오지 못했습니다.",
        )


@app.post(
    "/api/accounts/{account_id}/cash-flows",
    status_code=201,
)
def create_cash_flow_api(
    account_id: int,
    request: CashFlowRequest,
    authorization: str | None = Header(default=None),
):
    user_id = get_verified_user_id(
        authorization
    )

    try:
        repo = Repository(
            user_id=user_id
        )

        account = repo.get_account(
            account_id
        )

        if account is None:
            raise HTTPException(
                status_code=404,
                detail="계좌를 찾을 수 없습니다.",
            )

        cash_flow = repo.create_cash_flow(
            account_id=account_id,
            flow_date=request.flow_date,
            flow_type=request.flow_type,
            amount=request.amount,
            currency=request.currency,
            memo=request.memo,
        )

        return {
            "created": True,

            "cash_flow": {
                "id":
                    cash_flow.id,

                "account_id":
                    cash_flow.account_id,

                "flow_date":
                    cash_flow
                    .flow_date
                    .isoformat(),

                "flow_type":
                    cash_flow.flow_type,

                "amount":
                    float(
                        cash_flow.amount
                        or 0
                    ),

                "currency":
                    cash_flow.currency,

                "memo":
                    cash_flow.memo
                    or "",
            },
        }

    except HTTPException:
        raise

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="입출금 내역을 저장하지 못했습니다.",
        )


@app.put(
    "/api/accounts/{account_id}/cash-flows/{cash_flow_id}"
)
def update_cash_flow_api(
    account_id: int,
    cash_flow_id: int,
    request: CashFlowRequest,
    authorization: str | None = Header(default=None),
):
    user_id = get_verified_user_id(
        authorization
    )

    try:
        repo = Repository(
            user_id=user_id
        )

        account = repo.get_account(
            account_id
        )

        if account is None:
            raise HTTPException(
                status_code=404,
                detail="계좌를 찾을 수 없습니다.",
            )

        cash_flows = repo.get_cash_flows(
            account_id
        )

        cash_flow_exists = any(
            cash_flow.id == cash_flow_id
            for cash_flow in cash_flows
        )

        if not cash_flow_exists:
            raise HTTPException(
                status_code=404,
                detail="입출금 내역을 찾을 수 없습니다.",
            )

        updated = repo.update_cash_flow(
            cash_flow_id=cash_flow_id,
            flow_date=request.flow_date,
            flow_type=request.flow_type,
            amount=request.amount,
            currency=request.currency,
            memo=request.memo,
        )

        if not updated:
            raise HTTPException(
                status_code=404,
                detail="입출금 내역을 찾을 수 없습니다.",
            )

        return {
            "updated": True,
            "cash_flow_id": cash_flow_id,
        }

    except HTTPException:
        raise

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="입출금 내역을 수정하지 못했습니다.",
        )


@app.delete(
    "/api/accounts/{account_id}/cash-flows/{cash_flow_id}"
)
def delete_cash_flow_api(
    account_id: int,
    cash_flow_id: int,
    authorization: str | None = Header(default=None),
):
    user_id = get_verified_user_id(
        authorization
    )

    try:
        repo = Repository(
            user_id=user_id
        )

        account = repo.get_account(
            account_id
        )

        if account is None:
            raise HTTPException(
                status_code=404,
                detail="계좌를 찾을 수 없습니다.",
            )

        cash_flows = repo.get_cash_flows(
            account_id
        )

        cash_flow_exists = any(
            cash_flow.id == cash_flow_id
            for cash_flow in cash_flows
        )

        if not cash_flow_exists:
            raise HTTPException(
                status_code=404,
                detail="입출금 내역을 찾을 수 없습니다.",
            )

        deleted = repo.delete_cash_flow(
            cash_flow_id=cash_flow_id
        )

        if not deleted:
            raise HTTPException(
                status_code=404,
                detail="입출금 내역을 찾을 수 없습니다.",
            )

        return {
            "deleted": True,
            "cash_flow_id": cash_flow_id,
        }

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="입출금 내역을 삭제하지 못했습니다.",
        )
        


# =========================================================
# 보유현황 API
# =========================================================

@app.get(
    "/api/accounts/{account_id}/positions"
)
def get_account_positions_api(
    account_id: int,
    authorization: str | None = Header(default=None),
):
    user_id = get_verified_user_id(
        authorization
    )

    try:
        repo = Repository(
            user_id=user_id
        )

        account = repo.get_account(
            account_id
        )

        if account is None:
            raise HTTPException(
                status_code=404,
                detail="계좌를 찾을 수 없습니다.",
            )

        account_currency = (
            str(
                account.currency
                or "KRW"
            )
            .strip()
            .upper()
        )

        portfolio_service = PortfolioService(
            repo=repo
        )

        # -----------------------------------------------------
        # 1. 계좌 보유 포지션 계산
        # -----------------------------------------------------

        positions = (
            portfolio_service
            .get_positions(
                account_id=account_id
            )
        )

        # -----------------------------------------------------
        # 2. 주식 포트폴리오 요약 계산
        #
        # 여기의 total_current_value는
        # 현금을 제외한 보유 종목의 평가금액입니다.
        # -----------------------------------------------------

        summary = (
            portfolio_service
            .get_summary(
                positions=positions,
                account_id=account_id,
            )
        )

        # -----------------------------------------------------
        # 3. 실제 현금잔고 계산
        #
        # 현금잔고 =
        # 초기투자금
        # + 추가입금
        # - 출금
        # - 매수대금
        # + 매도대금
        # + 배당 실수령액
        # -----------------------------------------------------

        cash_balance = (
            portfolio_service
            .get_cash_balance(
                account_id=account_id,
                include_initial_capital=True,
            )
        )

        # -----------------------------------------------------
        # 4. 실제 총자산 계산
        #
        # 총자산 =
        # 주식 평가금액 + 현금잔고
        # -----------------------------------------------------

        securities_value = float(
            summary.total_current_value
            or 0
        )

        total_assets = (
            securities_value
            + float(
                cash_balance
                or 0
            )
        )

        # -----------------------------------------------------
        # 5. 목표 비중
        # -----------------------------------------------------

        targets = repo.get_account_targets(
            account_id=account_id
        )

        target_weights = {
            target.ticker:
                float(
                    target.target_weight
                    or 0
                )
            for target in targets
        }

        # -----------------------------------------------------
        # 6. 종목별 평가금액을
        #    계좌 기준통화로 환산
        # -----------------------------------------------------

        converted_values = {}

        for ticker, position in (
            positions.items()
        ):
            asset_currency = (
                str(
                    position.currency
                    or account_currency
                )
                .strip()
                .upper()
            )

            converted_values[ticker] = (
                portfolio_service
                .convert_amount(
                    value=float(
                        position.current_value
                        or 0
                    ),
                    from_currency=(
                        asset_currency
                    ),
                    to_currency=(
                        account_currency
                    ),
                )
            )

        # 종목 비중은 현금을 제외한
        # 주식 평가금액을 기준으로 유지합니다.
        #
        # 따라서 종목 비중의 합은 100%가 됩니다.

        total_current_value = (
            securities_value
        )

        # -----------------------------------------------------
        # 7. 종목별 응답 생성
        # -----------------------------------------------------

        position_list = []

        for ticker, position in (
            positions.items()
        ):
            asset_currency = (
                str(
                    position.currency
                    or account_currency
                )
                .strip()
                .upper()
            )

            native_current_value = float(
                position.current_value
                or 0
            )

            account_current_value = float(
                converted_values.get(
                    ticker,
                    0.0,
                )
            )

            if total_current_value > 0:
                current_weight = (
                    account_current_value
                    / total_current_value
                )
            else:
                current_weight = 0.0

            position_list.append(
                {
                    "ticker":
                        position.ticker,

                    "name":
                        position.name,

                    # 종목 자체 통화
                    "currency":
                        asset_currency,

                    # 계좌 기준통화
                    "account_currency":
                        account_currency,

                    "quantity":
                        float(
                            position.quantity
                            or 0
                        ),

                    # 아래 가격과 금액은
                    # 종목 원래 통화 기준
                    "average_buy_price":
                        float(
                            position.average_buy_price
                            or 0
                        ),

                    "total_buy_cost":
                        float(
                            position.total_buy_cost
                            or 0
                        ),

                    "current_price":
                        float(
                            position.current_price
                            or 0
                        ),

                    "current_value":
                        native_current_value,

                    "unrealized_pnl":
                        float(
                            position.unrealized_pnl
                            or 0
                        ),

                    "unrealized_roi":
                        float(
                            position.unrealized_roi
                            or 0
                        ),

                    # 계좌 기준통화로 환산한 평가금액
                    "account_current_value":
                        account_current_value,

                    "current_weight":
                        current_weight,

                    "target_weight":
                        target_weights.get(
                            position.ticker,
                            0.0,
                        ),
                }
            )

        position_list.sort(
            key=lambda item: item["ticker"]
        )

        # -----------------------------------------------------
        # 8. 웹에 전달
        # -----------------------------------------------------

        return {
            "account_id":
                account.id,

            "account_name":
                account.account_name,

            "currency":
                account_currency,

            "summary": {
                "currency":
                    summary.currency,

                "initial_capital":
                    float(
                        summary.initial_capital
                        or 0
                    ),

                "total_invested":
                    float(
                        summary.total_invested
                        or 0
                    ),

                # 현금을 제외한 주식 평가금액
                "total_current_value":
                    securities_value,

                # 실제 현금잔고
                "cash_balance":
                    float(
                        cash_balance
                        or 0
                    ),

                # 주식 평가금액 + 실제 현금잔고
                "total_assets":
                    float(
                        total_assets
                        or 0
                    ),

                "total_unrealized_pnl":
                    float(
                        summary.total_unrealized_pnl
                        or 0
                    ),

                "total_realized_pnl":
                    float(
                        summary.total_realized_pnl
                        or 0
                    ),

                "total_dividends":
                    float(
                        summary.total_dividends
                        or 0
                    ),

                "total_pnl":
                    float(
                        summary.total_pnl
                        or 0
                    ),

                "total_roi":
                    float(
                        summary.total_roi
                        or 0
                    ),

                # 기존 필드는 프런트엔드 호환성을 위해
                # 남겨두되 실제 현금잔고로 변경합니다.
                "remaining_cash":
                    float(
                        cash_balance
                        or 0
                    ),

                "position_count":
                    int(
                        summary.position_count
                        or 0
                    ),
            },

            # 기존 프런트엔드와의 호환성을 위해
            # 현금을 제외한 주식 평가금액을 유지합니다.
            "total_current_value":
                securities_value,

            # 앞으로 사용할 명확한 최상위 값도 제공합니다.
            "cash_balance":
                float(
                    cash_balance
                    or 0
                ),

            "total_assets":
                float(
                    total_assets
                    or 0
                ),

            "positions":
                position_list,
        }

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="보유현황을 계산하지 못했습니다.",
        )
        
# =========================================================
# 모바일 웹 UI
# =========================================================

@app.get("/", response_class=HTMLResponse)
def home():
    supabase_url = os.getenv(
        "SUPABASE_URL",
        "",
    ).strip()

    supabase_key = os.getenv(
        "SUPABASE_ANON_KEY",
        "",
    ).strip()

    if not supabase_url or not supabase_key:
        return HTMLResponse(
            content="""
            <h1>웹 설정 오류</h1>
            <p>Supabase 웹 인증 설정이 없습니다.</p>
            """,
            status_code=500,
        )

    html = """
<!DOCTYPE html>

<html lang="ko">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0, viewport-fit=cover"
>

<title>RetirementPortfolio</title>

<style>

* {
    box-sizing: border-box;
}

html {
    overflow-x: hidden;
    -webkit-text-size-adjust: 100%;
}

body {
    margin: 0;
    padding:
        max(14px, env(safe-area-inset-top))
        max(12px, env(safe-area-inset-right))
        max(56px, env(safe-area-inset-bottom))
        max(12px, env(safe-area-inset-left));
    background: #f5f7fa;
    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;
    color: #202124;
    overflow-x: hidden;
}

.container {
    width: 100%;
    max-width: 920px;
    margin: 8px auto 24px;
}

.card {
    background: white;
    border-radius: 18px;
    padding: 24px 20px;
    margin-bottom: 16px;
    box-shadow:
        0 2px 14px rgba(0,0,0,0.08);
    min-width: 0;
    overflow-wrap: anywhere;
}

h1 {
    margin: 0 0 8px;
    font-size: 25px;
}

h2 {
    margin: 0 0 16px;
    font-size: 20px;
}

.subtitle {
    margin: 0 0 20px;
    color: #666;
    line-height: 1.5;
}

label {
    display: block;
    margin: 14px 0 7px;
    font-weight: 600;
    font-size: 14px;
}

input,
select,
textarea {
    width: 100%;
    min-height: 48px;
    padding: 12px;
    border: 1px solid #d5d9df;
    border-radius: 10px;
    background: white;
    font-size: 16px;
    color: #202124;
}

input:focus-visible,
select:focus-visible,
textarea:focus-visible,
button:focus-visible,
.position-row:focus-visible {
    outline: 3px solid rgba(26, 115, 232, 0.32);
    outline-offset: 2px;
}

textarea {
    min-height: 80px;
    resize: vertical;
}

button {
    width: 100%;
    min-height: 48px;
    margin-top: 16px;
    border: 0;
    border-radius: 10px;
    background: #202124;
    color: white;
    font-size: 15px;
    font-weight: 700;
    cursor: pointer;
    touch-action: manipulation;
}

button:disabled {
    opacity: 0.55;
    cursor: not-allowed;
}

.secondary-button {
    background: #4b5563;
}

.delete-button {
    background: #b3261e;
}

.cancel-button {
    background: #777;
}

.small-button {
    width: auto;
    min-height: 36px;
    margin: 0;
    padding: 7px 14px;
    font-size: 13px;
}

#message {
    min-height: 24px;
    margin-top: 16px;
}

.success {
    color: #137333;
}

.error {
    color: #b3261e;
}

.empty,
.loading {
    color: #777;
    font-size: 13px;
    padding: 10px 0;
}

#app-area {
    display: none;
    flex-direction: column;
}

#app-header { order: 0; }
#portfolio-section { order: 1; }
#investment-settings-section { order: 2; }
#asset-search-section { order: 3; }

#boot-screen {
    display: none;
    min-height: 55vh;
    align-items: center;
    justify-content: center;
    color: #5f6368;
    text-align: center;
}

.boot-spinner {
    width: 30px;
    height: 30px;
    margin: 0 auto 12px;
    border: 3px solid #dfe3e8;
    border-top-color: #1a73e8;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
}

@keyframes spin {
    to { transform: rotate(360deg); }
}

.status-box {
    padding: 14px;
    background: #f1f8f4;
    border-radius: 10px;
    line-height: 1.6;
    font-size: 14px;
}

.account-card {
    margin-top: 14px;
    padding: 17px;
    border: 1px solid #e1e4e8;
    border-radius: 14px;
}

.account-name {
    font-size: 18px;
    font-weight: 700;
}

.account-detail {
    margin-top: 5px;
    color: #555;
    font-size: 14px;
    line-height: 1.5;
    min-width: 0;
    overflow-wrap: anywhere;
}

.account-summary-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
    padding: 4px 0 10px;
}

.summary-kpi {
    min-width: 0;
    padding: 12px;
    border: 1px solid #e7e9ed;
    border-radius: 12px;
    background: #f8fafc;
}

.summary-kpi-label {
    color: #68707b;
    font-size: 12px;
    font-weight: 650;
}

.summary-kpi-value {
    margin-top: 5px;
    font-size: clamp(15px, 4.5vw, 21px);
    font-weight: 800;
    line-height: 1.25;
    overflow-wrap: anywhere;
}

.account-summary-grid > .account-detail {
    grid-column: 1 / -1;
    margin-top: 0;
}

.section-title {
    margin-top: 20px;
    padding-top: 16px;
    border-top: 1px solid #eee;
    font-size: 15px;
    font-weight: 700;
}

.target-row {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    padding: 10px 0;
    border-bottom: 1px solid #f0f0f0;
}

.target-info {
    min-width: 0;
}

.target-name {
    font-size: 14px;
    font-weight: 600;
}

.target-ticker {
    margin-top: 3px;
    color: #777;
    font-size: 13px;
}

.target-weight {
    flex-shrink: 0;
    font-size: 16px;
    font-weight: 700;
}

.transaction-form,
.account-editor {
    margin-top: 12px;
    padding: 14px;
    background: #f8f9fa;
    border-radius: 12px;
}

.form-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
}

  .transaction-add-button {
    width: auto;
    margin: 0 0 14px;
}

.transaction-entry-panel {
    margin-bottom: 16px;
    padding: 14px;
    border: 1px solid #e1e4e8;
    border-radius: 14px;
    background: #f8fafc;
}

.transaction-entry-panel[hidden] {
    display: none !important;
}

.transaction-entry-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 10px;
}

.transaction-entry-header .small-button {
    width: auto;
    margin: 0;
}

.transaction-filter-grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(180px, 1.5fr);
    gap: 8px;
    margin-bottom: 14px;
}

.transaction-filter-grid input,
.transaction-filter-grid select {
    margin: 0;
}

.transaction-row {
    padding: 11px 0;
    border-bottom: 1px solid #eee;
}

.transaction-main {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    font-size: 14px;
    font-weight: 600;
    min-width: 0;
}

.position-name {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.position-value {
    flex: 0 1 auto;
    min-width: 0;
    text-align: right;
    overflow-wrap: anywhere;
}

.transaction-detail {
    margin-top: 4px;
    color: #666;
    font-size: 13px;
}

.transaction-actions {
    display: flex;
    gap: 8px;
    margin-top: 9px;
}

.transaction-actions button {
    flex: 1 1 0;
    min-height: 44px;
}

.buy {
    color: #b3261e;
}

.sell {
    color: #137333;
}

 .transaction-list-controls {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    margin-top: 12px;
}

.transaction-list-count {
    color: #777;
    font-size: 12px;
}

.transaction-list-controls .small-button {
    flex: 0 0 auto;
    margin: 0;
}

.transaction-message {
    min-height: 20px;
    margin-top: 12px;
    font-size: 13px;
}

.security {
    margin-top: 22px;
    padding-top: 16px;
    border-top: 1px solid #eee;
    color: #777;
    font-size: 13px;
    line-height: 1.6;
}

.settings-summary {
    margin-top: 10px;
    padding: 11px;
    background: #f8f9fa;
    border-radius: 10px;
}

.settings-subnav {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 7px;
    margin-bottom: 12px;
}

.settings-subnav button {
    min-width: 0;
    min-height: 44px;
    margin: 0;
    padding: 8px 5px;
    border-radius: 10px;
    background: #f3f5f7;
    color: #68707b;
    font-size: 12px;
}

.settings-subnav button.active {
    background: #202124;
    color: white;
}

.checkbox-row {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 14px;
}

.checkbox-row input {
    width: auto;
    min-height: auto;
}

.checkbox-row label {
    margin: 0;
}

.position-row {
    cursor: pointer;
    border-radius: 12px;
    transition:
        background 0.15s ease;
    padding: 14px 10px;
    border: 1px solid #edf0f3;
    margin-bottom: 10px;
}

.position-row:active {
    background: #f8f9fa;
}

.position-chart-hint {
    margin-top: 8px;
    color: #8a8f98;
    font-size: 12px;
}

.asset-chart-panel {
    margin: 10px 0 16px;
    padding: 14px;
    background: #f8f9fa;
    border: 1px solid #eceff3;
    border-radius: 14px;
    max-width: 100%;
    overflow: hidden;
}

.asset-chart-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 12px;
}

.asset-chart-title {
    min-width: 0;
}

.asset-chart-name {
    font-size: 15px;
    font-weight: 700;
}

.asset-chart-ticker {
    margin-top: 3px;
    color: #777;
    font-size: 12px;
}

.asset-chart-close {
    width: auto;
    min-width: 34px;
    min-height: 34px;
    margin: 0;
    padding: 5px 10px;
    background: #e7e9ed;
    color: #444;
    font-size: 16px;
}
.asset-chart-period-buttons {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 5px;
    margin: 4px 0 14px;
}

.asset-chart-period-button {
    width: 100%;
    min-width: 0;
    min-height: 34px;
    margin: 0;
    padding: 6px 3px;
    border: 1px solid #e1e4e8;
    border-radius: 8px;
    background: white;
    color: #666;
    font-size: 12px;
    font-weight: 600;
}

.asset-chart-period-button.active {
    border-color: #202124;
    background: #202124;
    color: white;
}

.asset-chart-summary {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 10px;
}

.asset-chart-price {
    font-size: 21px;
    font-weight: 700;
}

.asset-chart-period {
    color: #777;
    font-size: 12px;
}

.asset-chart-container {
    position: relative;
    width: 100%;
    height: 230px;
    overflow: hidden;
    background: white;
    border-radius: 12px;
}

.asset-chart-svg {
    display: block;
    width: 100%;
    height: 100%;
    touch-action: pan-y;
}

.asset-chart-empty {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 230px;
    color: #777;
    font-size: 13px;
}

.asset-chart-legend {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    margin-top: 11px;
    color: #666;
    font-size: 12px;
}

.asset-chart-legend-item {
    display: flex;
    align-items: center;
    gap: 5px;
}

.asset-chart-marker {
    width: 8px;
    height: 8px;
    border-radius: 50%;
}

.asset-chart-marker.buy-marker {
    background: #b3261e;
}

.asset-chart-marker.sell-marker {
    background: #137333;
}

.asset-chart-tooltip {
    display: none;
    margin-top: 10px;
    padding: 10px 12px;
    background: white;
    border: 1px solid #e1e4e8;
    border-radius: 10px;
    font-size: 12px;
    line-height: 1.6;
}

.asset-chart-tooltip.visible {
    display: block;
}

.asset-chart-crosshair {
    pointer-events: none;
}

.asset-chart-touch-line {
    stroke: #9aa0a6;
    stroke-width: 1;
    stroke-dasharray: 4 3;
    vector-effect: non-scaling-stroke;
}

.asset-chart-touch-point {
    fill: #ffffff;
    stroke: #202124;
    stroke-width: 2;
    vector-effect: non-scaling-stroke;
}

.asset-chart-touch-label {
    position: absolute;
    z-index: 20;
    display: none;
    padding: 7px 9px;
    border-radius: 8px;
    background: rgba(32, 33, 36, 0.92);
    color: #ffffff;
    font-size: 12px;
    line-height: 1.4;
    white-space: nowrap;
    pointer-events: none;
    transform: translateX(-50%);
}

.asset-chart-touch-label.visible {
    display: block;
}

.asset-chart-loading {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 230px;
    color: #777;
    font-size: 13px;
}


.app-bottom-nav {
    position: fixed;
    left: 50%;
    bottom: 0;
    z-index: 1000;
    display: grid;
    width: min(920px, 100%);
    transform: translateX(-50%);
    grid-auto-flow: column;
    grid-auto-columns: minmax(0, 1fr);
    padding: 7px max(8px, env(safe-area-inset-right)) max(7px, env(safe-area-inset-bottom)) max(8px, env(safe-area-inset-left));
    border-top: 1px solid #e1e4e8;
    background: rgba(255,255,255,0.96);
    backdrop-filter: blur(12px);
}

.app-bottom-nav button {
    min-height: 48px;
    margin: 0;
    padding: 5px 2px;
    border-radius: 10px;
    background: transparent;
    color: #68707b;
    font-size: 12px;
}

.app-bottom-nav button.active {
    background: #eef3f8;
    color: #202124;
}

.app-tab-section[hidden] {
    display: none !important;
}

body { padding-bottom: max(92px, calc(env(safe-area-inset-bottom) + 78px)); }

@media (max-width: 600px) {
    .form-row,
    .transaction-filter-grid {
        grid-template-columns: 1fr;
        gap: 8px;
    }

    .settings-subnav {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .card {
        padding: 18px 14px;
        border-radius: 15px;
        margin-bottom: 12px;
    }

    .account-card {
        padding: 14px;
    }

    .asset-chart-container,
    .asset-chart-empty,
    .asset-chart-loading {
        height: 210px;
    }

    .asset-chart-header,
    .asset-chart-summary {
        flex-wrap: wrap;
    }

    .asset-chart-close {
        min-width: 44px;
        min-height: 44px;
    }

    .small-button,
    .asset-chart-period-button {
        min-height: 44px;
    }

    .transaction-actions {
        flex-wrap: wrap;
    }

    .transaction-actions button {
        flex: 1 1 120px;
    }

    .asset-chart-panel {
        padding: 12px 10px;
    }
}

@media (min-width: 768px) {
    .account-summary-grid {
        grid-template-columns: repeat(auto-fit, minmax(64px, 1fr));
    }

    .form-row {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
}

@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        scroll-behavior: auto !important;
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
    }
}

</style>

</head>


<body>

<main class="container">

<section id="boot-screen" aria-live="polite" aria-busy="true">
    <div>
        <div class="boot-spinner" aria-hidden="true"></div>
        로그인 상태를 확인하고 있습니다.
    </div>
</section>

<section
    id="login-card"
    class="card"
>

<h1>RetirementPortfolio</h1>

<p class="subtitle">
포트폴리오 관리를 위해 로그인하세요.
</p>

<form id="login-form">

<label for="email">
이메일
</label>

<input
    id="email"
    type="email"
    autocomplete="email"
    required
>

<label for="password">
비밀번호
</label>

<input
    id="password"
    type="password"
    autocomplete="current-password"
    required
>

<button
    id="login-button"
    type="submit"
>
로그인
</button>

</form>

<button
    id="show-signup-button"
    type="button"
    class="secondary-button"
    style="display:none;"
>
회원가입
</button>

<form
    id="signup-form"
    style="display:none;margin-top:18px;"
>
<label for="signup-email">
이메일
</label>
<input
    id="signup-email"
    type="email"
    autocomplete="email"
    required
>

<label for="signup-password">
비밀번호 (8자 이상)
</label>
<input
    id="signup-password"
    type="password"
    minlength="8"
    autocomplete="new-password"
    required
>

<button
    id="signup-button"
    type="submit"
>
회원가입
</button>
</form>

<div id="message"></div>

<div class="security">
비밀번호 인증은 Supabase Auth가 처리하며
포트폴리오 데이터베이스에는 비밀번호를
저장하지 않습니다.
</div>

</section>


<div id="app-area">

<section id="app-header" class="card">

<h1>RetirementPortfolio</h1>

<div
    id="login-status"
    class="status-box"
>
로그인 완료
</div>

</section>

<section id="report-section" class="card" style="display:none;padding:0;overflow:hidden;">
<div id="report-message" class="status-box">모닝 리포트를 불러오는 중...</div>
<iframe id="report-frame" title="내 모닝 리포트" sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox" style="display:none;width:100%;height:85vh;border:0;"></iframe>
</section>


<section id="admin-section" class="card" style="display:none;">
<h2>관리자 · 회원 관리</h2>
<p class="subtitle">신규 회원가입 허용 여부와 회원 이용 권한을 관리합니다. 다른 회원의 보유종목, 투자금액, 매매내역 등 투자 데이터는 이 화면에서 열람할 수 없습니다.</p>
<div class="security">실제 계좌번호 전체, 증권사 비밀번호, 인증번호, API 비밀키 등 민감한 정보는 RetirementPortfolio에 입력하지 마세요.</div>

<div class="status-box" style="margin-bottom:18px;">
<strong>신규 회원가입</strong><br>
<label class="checkbox-row" style="margin-top:10px;">
<input id="admin-signup-enabled" type="checkbox">
<span>회원가입 허용</span>
</label>
<p id="admin-signup-status" aria-live="polite"></p>
</div>

<h3>회원</h3>
<div id="admin-members">불러오는 중...</div>
</section>

<section id="settings-navigation-section" class="card" hidden>
<h2>설정</h2>
<div id="settings-subnav" class="settings-subnav" aria-label="설정 메뉴">
<button type="button" data-settings-panel="accounts" class="active" aria-current="page">계좌</button>
<button type="button" data-settings-panel="report">리포트</button>
<button type="button" data-settings-panel="kakao">카카오</button>
<button type="button" data-settings-panel="strategy">투자전략</button>
</div>
<button id="logout-button" type="button" class="secondary-button">로그아웃</button>
</section>

<section id="morning-report-settings-section" class="card">
<h2>모닝 리포트 설정</h2>
<p class="subtitle">사용자별 발송 여부와 기준 시간을 설정합니다. 실제 실행은 약 10분 간격 스케줄에 따라 지연될 수 있습니다.</p>
<form id="morning-report-settings-form">
<div class="checkbox-row">
<input id="morning-report-enabled" type="checkbox">
<label for="morning-report-enabled">모닝 리포트 사용</label>
</div>
<label for="morning-report-time">발송 기준 시간</label>
<input id="morning-report-time" type="time" required>
<div class="checkbox-row">
<input id="morning-report-news-enabled" type="checkbox">
<label for="morning-report-news-enabled">뉴스 포함</label>
</div>
<button type="submit">모닝 리포트 설정 저장</button>
<div id="morning-report-settings-message" class="transaction-message"></div>
</form>
</section>

<section id="kakao-settings-section" class="card">

<h2>카카오톡 모닝 리포트</h2>
<p class="subtitle">
토큰을 직접 입력할 필요 없이 카카오 계정을 한 번 연결하면 됩니다.
</p>
<div id="kakao-status" class="status-box">연결 상태 확인 중...</div>
<button id="kakao-connect-button" type="button">카카오톡 연결</button>\n<button id="kakao-test-button" type="button" style="display:none;">테스트 메시지 보내기</button>\n<button id="kakao-disconnect-button" type="button" style="display:none;">카카오톡 연결 해제</button>

</section>

<section id="investment-settings-section" class="card">

<h2>투자성향 / 투자전략</h2>

<p class="subtitle">
사용자 전체의 장기 투자성향과 AI 분석 원칙입니다.
계좌별 투자금과 매수 한도는 각 계좌 설정에서 관리합니다.
</p>

<form id="investment-profile-form">

<label for="risk-profile">
투자 성향
</label>

<select id="risk-profile">

<option value="conservative">
안정형
</option>

<option value="balanced">
균형형
</option>

<option value="aggressive">
공격형
</option>

</select>


<label for="investment-horizon">
투자기간 (년)
</label>

<input
    id="investment-horizon"
    type="number"
    min="0"
    max="100"
    placeholder="예: 12"
>


<label for="ai-advice-style">
AI 조언 방식
</label>

<select id="ai-advice-style">

<option value="conservative">
보수적
</option>

<option value="balanced">
균형적
</option>

<option value="aggressive">
적극적
</option>

</select>

<div class="checkbox-row">

<input
    id="ai-advice-enabled"
    type="checkbox"
    checked
>

<label for="ai-advice-enabled">
Gemini AI 투자 가이드 사용
</label>

</div>

<label for="investment-preference-text">
나의 투자 원칙 / 전략
</label>

<textarea
    id="investment-preference-text"
    style="min-height:180px;"
    placeholder="장기투자 원칙, 분할매수 기준, 급락 시 대응 원칙 등을 입력하세요."
></textarea>


<button type="submit">
투자전략 저장
</button>

<div
    id="investment-profile-message"
    class="transaction-message"
></div>

</form>

</section>


<section id="asset-search-section" class="card">

<h2>미국 종목 검색</h2>

<p class="subtitle">
미국 주식 또는 ETF의 티커를 입력하면
Yahoo Finance에서 종목 정보를 확인합니다.
아직 포트폴리오에는 저장되지 않습니다.
</p>

<form id="us-asset-search-form">

<label for="us-asset-ticker">
미국 종목 티커
</label>

<input
    id="us-asset-ticker"
    type="text"
    maxlength="30"
    placeholder="예: AAPL, MSFT, QQQ"
    autocomplete="off"
    autocapitalize="characters"
    required
>

<button
    id="us-asset-search-button"
    type="submit"
>
종목 검색
</button>

<div
    id="us-asset-search-result"
    class="transaction-message"
></div>

</form>

</section>



<section id="transactions-section" class="card" hidden>
<h2>거래</h2>
<p class="subtitle">모든 계좌의 거래를 한 곳에서 확인합니다.</p>
<button id="open-transaction-entry" type="button" class="transaction-add-button">＋ 거래 추가</button>
<div id="transaction-entry-panel" class="transaction-entry-panel" hidden>
<div class="transaction-entry-header"><strong>새 거래 입력</strong><button id="close-transaction-entry" type="button" class="small-button secondary-button">닫기</button></div>
<label for="transaction-entry-account">계좌</label>
<select id="transaction-entry-account"><option value="">계좌를 선택하세요</option></select>
<div id="transaction-entry-form"></div>
</div>
<div class="transaction-filter-grid">
<select id="transaction-account-filter" aria-label="계좌 필터"><option value="">전체 계좌</option></select>
<select id="transaction-type-filter" aria-label="거래 유형 필터"><option value="">전체 거래</option><option value="BUY">매수</option><option value="SELL">매도</option></select>
<input id="transaction-search-filter" type="search" placeholder="종목명 또는 티커 검색" aria-label="종목 검색">
</div>
<div id="all-transactions-list" class="loading">거래 내역을 불러오는 중...</div>
<div class="section-title">입금 / 출금</div>
<button id="open-cash-flow-entry" type="button" class="transaction-add-button">＋ 입출금 추가</button>
<div id="cash-flow-entry-panel" class="transaction-entry-panel" hidden>
<div class="transaction-entry-header"><strong>새 입출금 입력</strong><button id="close-cash-flow-entry" type="button" class="small-button secondary-button">닫기</button></div>
<label for="cash-flow-entry-account">계좌</label>
<select id="cash-flow-entry-account"><option value="">계좌를 선택하세요</option></select>
<div id="cash-flow-entry-form"></div>
</div>
<div id="all-cash-flows-list" class="loading">입출금 내역을 불러오는 중...</div>
</section>

<section id="portfolio-section" class="card">

<h2>내 계좌</h2>

<div id="accounts-list"></div>

</section>

<section id="account-management-section" class="card" hidden>
<h2>계좌 관리</h2>
<p class="subtitle">계좌 정보 변경과 계좌 삭제를 관리합니다. 계좌 삭제는 관련 거래·입출금·배당·목표 포트폴리오도 함께 삭제합니다.</p>
<div id="account-creator"></div>
<div id="account-management-list"></div>
</section>


<nav id="app-bottom-nav" class="app-bottom-nav" aria-label="주요 메뉴">
<button type="button" data-app-tab="home" class="active" aria-current="page">홈</button>
<button type="button" data-app-tab="portfolio">포트폴리오</button>
<button type="button" data-app-tab="transactions">거래</button>
<button type="button" data-app-tab="settings">설정</button>
<button id="member-management-tab-button" type="button" data-app-tab="members" hidden>회원관리</button>
</nav>

</div>

</main>


<script>

const SUPABASE_URL =
    __SUPABASE_URL_JSON__;

const SUPABASE_KEY =
    __SUPABASE_KEY_JSON__;



const loginCard =
    document.getElementById(
        "login-card"
    );

const bootScreen =
    document.getElementById(
        "boot-screen"
    );

const loginForm =
    document.getElementById(
        "login-form"
    );

const loginButton =
    document.getElementById(
        "login-button"
    );

const showSignupButton =
    document.getElementById(
        "show-signup-button"
    );

const signupForm =
    document.getElementById(
        "signup-form"
    );

const signupButton =
    document.getElementById(
        "signup-button"
    );

const message =
    document.getElementById(
        "message"
    );

const appArea =
    document.getElementById(
        "app-area"
    );


const appBottomNav = document.getElementById("app-bottom-nav");
const appTabSections = {
    home: ["app-header", "report-section"],
    portfolio: ["portfolio-section", "asset-search-section"],
    transactions: ["transactions-section"],
    settings: ["settings-navigation-section", "account-management-section", "morning-report-settings-section", "kakao-settings-section", "investment-settings-section"],
    members: ["admin-section"],
};
let activeAppTab = "home";
let activeSettingsPanel = "accounts";
const settingsPanels = {
    accounts: "account-management-section",
    report: "morning-report-settings-section",
    kakao: "kakao-settings-section",
    strategy: "investment-settings-section",
};

function applySettingsPanel() {
    const settingsActive = activeAppTab === "settings";
    for (const [panelName, sectionId] of Object.entries(settingsPanels)) {
        const section = document.getElementById(sectionId);
        if (section) section.hidden = !settingsActive || panelName !== activeSettingsPanel;
    }
    const settingsNavigation = document.getElementById("settings-navigation-section");
    if (settingsNavigation) settingsNavigation.hidden = !settingsActive;
    const settingsSubnav = document.getElementById("settings-subnav");
    if (!settingsSubnav) return;
    for (const button of settingsSubnav.querySelectorAll("[data-settings-panel]")) {
        const active = button.dataset.settingsPanel === activeSettingsPanel;
        button.classList.toggle("active", active);
        if (active) button.setAttribute("aria-current", "page");
        else button.removeAttribute("aria-current");
    }
}

function setSettingsPanel(panelName, options = {}) {
    if (!settingsPanels[panelName]) return;
    activeSettingsPanel = panelName;
    applySettingsPanel();
    if (options.scroll !== false) window.scrollTo({top: 0, behavior: "smooth"});
}

function setAppTab(tabName, options = {}) {
    const nextTab = appTabSections[tabName] ? tabName : "home";
    activeAppTab = nextTab;
    const allIds = new Set(Object.values(appTabSections).flat());
    for (const id of allIds) {
        const section = document.getElementById(id);
        if (!section) continue;
        section.hidden = !appTabSections[nextTab].includes(id);
    }
    if (nextTab === "settings") applySettingsPanel();
    for (const button of appBottomNav.querySelectorAll("[data-app-tab]")) {
        const active = button.dataset.appTab === nextTab;
        button.classList.toggle("active", active);
        if (active) button.setAttribute("aria-current", "page");
        else button.removeAttribute("aria-current");
    }
    if (options.scroll !== false) window.scrollTo({top: 0, behavior: "smooth"});
}

appBottomNav.addEventListener("click", (event) => {
    const button = event.target.closest("[data-app-tab]");
    if (!button) return;
    setAppTab(button.dataset.appTab);
});

document.getElementById("settings-subnav").addEventListener("click", (event) => {
    const button = event.target.closest("[data-settings-panel]");
    if (!button) return;
    setSettingsPanel(button.dataset.settingsPanel);
});


const openTransactionEntry = document.getElementById("open-transaction-entry");
const closeTransactionEntry = document.getElementById("close-transaction-entry");
const transactionEntryPanel = document.getElementById("transaction-entry-panel");
const transactionEntryAccount = document.getElementById("transaction-entry-account");
const transactionEntryForm = document.getElementById("transaction-entry-form");
let transactionTabAccounts = [];
let transactionTabAccessToken = "";

async function refreshPortfolioAfterTransactionChange() {
    if (!transactionTabAccessToken || !transactionTabAccounts.length) return;
    await renderAccounts(transactionTabAccounts, transactionTabAccessToken);
}

async function showTransactionEntryForm() {
    transactionEntryForm.className = "";
    transactionEntryForm.innerHTML = "";
    const account = transactionTabAccounts.find((item) => String(item.id) === transactionEntryAccount.value);
    if (!account) return;
    transactionEntryForm.innerHTML = '<div class="loading">입력폼을 준비하는 중...</div>';
    try {
        const targets = await loadAccountTargets(transactionTabAccessToken, account.id);
        transactionEntryForm.innerHTML = "";
        const form = createTransactionForm(
            account,
            targets,
            transactionTabAccessToken,
            null,
            null,
            {
                onSaved: async () => {
                    await loadTransactionTab(transactionTabAccounts, transactionTabAccessToken);
                    await refreshPortfolioAfterTransactionChange();
                    transactionEntryPanel.hidden = true;
                    transactionEntryAccount.value = "";
                    transactionEntryForm.className = "";
                    transactionEntryForm.innerHTML = "";
                },
            }
        );
        transactionEntryForm.appendChild(form);
    } catch (error) {
        transactionEntryForm.className = "error";
        transactionEntryForm.textContent = error.message || "거래 입력폼을 준비하지 못했습니다.";
    }
}

openTransactionEntry.addEventListener("click", () => {
    transactionEntryPanel.hidden = false;
    transactionEntryPanel.scrollIntoView({behavior: "smooth", block: "start"});
});
closeTransactionEntry.addEventListener("click", () => {
    transactionEntryPanel.hidden = true;
    transactionEntryForm.className = "";
    transactionEntryForm.innerHTML = "";
    transactionEntryAccount.value = "";
});
transactionEntryAccount.addEventListener("change", showTransactionEntryForm);

const openCashFlowEntry = document.getElementById("open-cash-flow-entry");
const closeCashFlowEntry = document.getElementById("close-cash-flow-entry");
const cashFlowEntryPanel = document.getElementById("cash-flow-entry-panel");
const cashFlowEntryAccount = document.getElementById("cash-flow-entry-account");
const cashFlowEntryForm = document.getElementById("cash-flow-entry-form");
const allCashFlowsList = document.getElementById("all-cash-flows-list");

async function loadCashFlowTab(accounts, accessToken) {
    cashFlowEntryAccount.innerHTML = '<option value="">계좌를 선택하세요</option>';
    const groups = await Promise.all(accounts.map(async (account) => ({
        account,
        cashFlows: await loadCashFlows(accessToken, account.id),
    })));
    allCashFlowsList.innerHTML = "";
    let count = 0;
    const selectedAccountId = transactionAccountFilter.value;
    for (const group of groups) {
        const option = document.createElement("option");
        option.value = String(group.account.id);
        option.textContent = group.account.name;
        cashFlowEntryAccount.appendChild(option);
        if (selectedAccountId && String(group.account.id) !== selectedAccountId) continue;
        if (!group.cashFlows.length) continue;
        const heading = document.createElement("div");
        heading.className = "section-title";
        heading.textContent = group.account.name;
        allCashFlowsList.appendChild(heading);
        const list = document.createElement("div");
        renderCashFlows(list, group.cashFlows, group.account, accessToken, {
            onChanged: async () => {
                await loadCashFlowTab(transactionTabAccounts, transactionTabAccessToken);
                await refreshPortfolioAfterTransactionChange();
            },
        });
        allCashFlowsList.appendChild(list);
        count += group.cashFlows.length;
    }
    allCashFlowsList.className = "";
    if (!count) allCashFlowsList.innerHTML = '<div class="empty">아직 등록된 입출금 내역이 없습니다.</div>';
}

async function showCashFlowEntryForm() {
    cashFlowEntryForm.innerHTML = "";
    const account = transactionTabAccounts.find((item) => String(item.id) === cashFlowEntryAccount.value);
    if (!account) return;
    const form = createCashFlowForm(account, transactionTabAccessToken, allCashFlowsList, {
        onSaved: async () => {
            await loadCashFlowTab(transactionTabAccounts, transactionTabAccessToken);
            await refreshPortfolioAfterTransactionChange();
            cashFlowEntryPanel.hidden = true;
            cashFlowEntryAccount.value = "";
            cashFlowEntryForm.innerHTML = "";
        },
    });
    cashFlowEntryForm.appendChild(form);
}

openCashFlowEntry.addEventListener("click", () => {
    cashFlowEntryPanel.hidden = false;
    cashFlowEntryPanel.scrollIntoView({behavior: "smooth", block: "start"});
});
closeCashFlowEntry.addEventListener("click", () => {
    cashFlowEntryPanel.hidden = true;
    cashFlowEntryAccount.value = "";
    cashFlowEntryForm.innerHTML = "";
});
cashFlowEntryAccount.addEventListener("change", showCashFlowEntryForm);

const transactionAccountFilter = document.getElementById("transaction-account-filter");
const transactionTypeFilter = document.getElementById("transaction-type-filter");
const transactionSearchFilter = document.getElementById("transaction-search-filter");
const allTransactionsList = document.getElementById("all-transactions-list");
let transactionTabRows = [];
let transactionTabVisibleCount = 20;

function renderTransactionTab() {
    const accountId = transactionAccountFilter.value;
    const type = transactionTypeFilter.value;
    const query = transactionSearchFilter.value.trim().toLowerCase();
    const filtered = transactionTabRows.filter((item) => {
        const transaction = item.transaction;
        if (accountId && String(item.account.id) !== accountId) return false;
        if (type && transaction.transaction_type !== type) return false;
        if (query) {
            const haystack = ((transaction.name || "") + " " + (transaction.ticker || "")).toLowerCase();
            if (!haystack.includes(query)) return false;
        }
        return true;
    });
    allTransactionsList.innerHTML = "";
    allTransactionsList.className = "";
    if (!filtered.length) {
        allTransactionsList.innerHTML = '<div class="empty">조건에 맞는 거래가 없습니다.</div>';
        return;
    }
    const visible = filtered.slice(0, transactionTabVisibleCount);
    for (const item of visible) {
        const transaction = item.transaction;
        const row = document.createElement("div");
        row.className = "transaction-row";
        const main = document.createElement("div");
        main.className = "transaction-main";
        const left = document.createElement("div");
        left.className = transaction.transaction_type === "BUY" ? "buy" : "sell";
        left.textContent = transaction.transaction_date + " · " + (transaction.name || transaction.ticker) + " (" + transaction.ticker + ") · " + (transaction.transaction_type === "BUY" ? "매수" : "매도");
        const amount = document.createElement("div");
        const currency = String(transaction.currency || getAccountCurrency(item.account)).toUpperCase();
        amount.textContent = formatMoney(Number(transaction.quantity) * Number(transaction.price), currency);
        main.append(left, amount);
        row.appendChild(main);
        row.appendChild(createDetail(item.account.name + " · 수량 " + formatNumber(transaction.quantity) + " · 체결가 " + formatMoney(transaction.price, currency)));

        const actions = document.createElement("div");
        actions.className = "transaction-actions";
        const editButton = document.createElement("button");
        editButton.type = "button";
        editButton.className = "small-button secondary-button";
        editButton.textContent = "수정";
        const deleteButton = document.createElement("button");
        deleteButton.type = "button";
        deleteButton.className = "small-button delete-button";
        deleteButton.textContent = "삭제";
        actions.append(editButton, deleteButton);
        row.appendChild(actions);

        editButton.addEventListener("click", async () => {
            editButton.disabled = true;
            try {
                const targets = await loadAccountTargets(transactionTabAccessToken, item.account.id);
                showTransactionEditor(
                    row,
                    transaction,
                    targets,
                    item.account,
                    transactionTabAccessToken,
                    null,
                    null,
                    {
                        onSaved: async () => {
                            await loadTransactionTab(transactionTabAccounts, transactionTabAccessToken);
                            await refreshPortfolioAfterTransactionChange();
                        },
                        onCancel: () => renderTransactionTab(),
                    }
                );
            } catch (error) {
                window.alert(error.message || "거래 수정 화면을 열지 못했습니다.");
                editButton.disabled = false;
            }
        });

        deleteButton.addEventListener("click", async () => {
            const assetName = transaction.name || transaction.ticker;
            if (!window.confirm(assetName + " 거래를 삭제할까요?")) return;
            deleteButton.disabled = true;
            try {
                await apiRequest(
                    "/api/accounts/" + item.account.id + "/transactions/" + transaction.id,
                    transactionTabAccessToken,
                    {method: "DELETE"}
                );
                await loadTransactionTab(transactionTabAccounts, transactionTabAccessToken);
                await refreshPortfolioAfterTransactionChange();
            } catch (error) {
                window.alert(error.message || "거래 삭제에 실패했습니다.");
                deleteButton.disabled = false;
            }
        });

        allTransactionsList.appendChild(row);
    }
    const controls = document.createElement("div");
    controls.className = "transaction-list-controls";
    const count = document.createElement("div");
    count.className = "transaction-list-count";
    count.textContent = "최근 " + visible.length + "건 / 검색 결과 " + filtered.length + "건";
    controls.appendChild(count);
    if (visible.length < filtered.length) {
        const more = document.createElement("button");
        more.type = "button"; more.className = "small-button secondary-button"; more.textContent = "20건 더 보기";
        more.addEventListener("click", () => { transactionTabVisibleCount += 20; renderTransactionTab(); });
        controls.appendChild(more);
    }
    allTransactionsList.appendChild(controls);
}

async function loadTransactionTab(accounts, accessToken) {
    transactionTabAccounts = accounts;
    transactionTabAccessToken = accessToken;
    transactionAccountFilter.innerHTML = '<option value="">전체 계좌</option>';
    transactionEntryAccount.innerHTML = '<option value="">계좌를 선택하세요</option>';
    for (const account of accounts) {
        const option = document.createElement("option"); option.value = String(account.id); option.textContent = account.name; transactionAccountFilter.appendChild(option);
        const entryOption = option.cloneNode(true); transactionEntryAccount.appendChild(entryOption);
    }
    const rows = await Promise.all(accounts.map(async (account) => {
        const transactions = await loadTransactions(accessToken, account.id);
        return transactions.map((transaction) => ({account, transaction}));
    }));
    transactionTabRows = rows.flat().sort((a, b) => String(b.transaction.transaction_date).localeCompare(String(a.transaction.transaction_date)) || Number(b.transaction.id || 0) - Number(a.transaction.id || 0));
    transactionTabVisibleCount = 20;
    renderTransactionTab();
    await loadCashFlowTab(accounts, accessToken);
}

transactionAccountFilter.addEventListener("change", async () => {
    transactionTabVisibleCount = 20;
    renderTransactionTab();
    await loadCashFlowTab(transactionTabAccounts, transactionTabAccessToken);
});
transactionTypeFilter.addEventListener("change", () => {
    transactionTabVisibleCount = 20;
    renderTransactionTab();
});
transactionSearchFilter.addEventListener("input", () => { transactionTabVisibleCount = 20; renderTransactionTab(); });

const loginStatus =
    document.getElementById(
        "login-status"
    );

const accountCreator = document.getElementById("account-creator");
const accountManagementList = document.getElementById("account-management-list");

const accountsList =
    document.getElementById(
        "accounts-list"
    );

const adminSection = document.getElementById("admin-section");
const memberManagementTabButton = document.getElementById("member-management-tab-button");
const adminMembers = document.getElementById("admin-members");
const adminSignupEnabled = document.getElementById("admin-signup-enabled");
const adminSignupStatus = document.getElementById("admin-signup-status");

function escapeAdminText(value) {
    const node = document.createElement("div");
    node.textContent = String(value ?? "");
    return node.innerHTML;
}

async function loadAdminPanel(accessToken) {
    const headers = {"Authorization": "Bearer " + accessToken};
    const statusResponse = await fetch("/api/admin/me", {headers});
    if (!statusResponse.ok) {
        memberManagementTabButton.hidden = true;
        adminSection.hidden = true;
        if (activeAppTab === "members") setAppTab("home", {scroll: false});
        return;
    }
    memberManagementTabButton.hidden = false;
    adminSection.style.display = "";
    adminSection.hidden = activeAppTab !== "members";
    const [membersResponse, signupResponse] = await Promise.all([
        fetch("/api/admin/members", {headers}),
        fetch("/api/signup-status"),
    ]);
    const membersData = await membersResponse.json();
    const signupData = await signupResponse.json();
    if (signupResponse.ok) {
        adminSignupEnabled.checked = Boolean(signupData.signup_enabled);
        adminSignupStatus.textContent = signupData.signup_enabled ? "현재 신규 회원가입을 허용하고 있습니다." : "현재 신규 회원가입이 중지되어 있습니다.";
    }
    if (membersResponse.ok) {
        adminMembers.innerHTML = (membersData.members || []).map((m) =>
            "<div class='status-box'><strong>" + escapeAdminText(m.email || "이메일 없음") + "</strong><br>"
            + "가입: " + escapeAdminText(m.created_at || "-") + " · "
            + (m.is_admin ? "관리자" : "일반회원") + " · "
            + (m.is_active ? "사용중" : "사용중지")
            + (m.is_admin ? "" : "<br><button type='button' class='small-button admin-toggle-member' data-id='" + escapeAdminText(m.user_id) + "' data-active='" + (m.is_active ? "true" : "false") + "'>" + (m.is_active ? "사용 중지" : "다시 활성화") + "</button> "
                + "<button type='button' class='small-button admin-delete-member' data-id='" + escapeAdminText(m.user_id) + "' data-email='" + escapeAdminText(m.email || "") + "'>로그인 계정 삭제</button>")
            + "</div>"
        ).join("") || "등록된 회원이 없습니다.";
    }
}

adminSignupEnabled.addEventListener("change", async () => {
    const accessToken = localStorage.getItem("access_token") || sessionStorage.getItem("access_token");
    if (!accessToken) return;
    adminSignupEnabled.disabled = true;
    try {
        const response = await fetch("/api/admin/signup-status", {
            method: "PUT",
            headers: {"Authorization": "Bearer " + accessToken, "Content-Type": "application/json"},
            body: JSON.stringify({enabled: adminSignupEnabled.checked}),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "회원가입 설정을 변경하지 못했습니다.");
        adminSignupStatus.textContent = data.signup_enabled ? "현재 신규 회원가입을 허용하고 있습니다." : "현재 신규 회원가입이 중지되어 있습니다.";
    } catch (error) {
        adminSignupEnabled.checked = !adminSignupEnabled.checked;
        adminSignupStatus.textContent = error.message || "회원가입 설정을 변경하지 못했습니다.";
    } finally {
        adminSignupEnabled.disabled = false;
    }
});

adminMembers.addEventListener("click", async (event) => {
    const button = event.target.closest(".admin-toggle-member, .admin-delete-member");
    if (!button) return;
    const accessToken = localStorage.getItem("access_token") || sessionStorage.getItem("access_token");
    if (!accessToken) return;
    if (button.classList.contains("admin-delete-member")) {
        const email = button.dataset.email || "이 회원";
        if (!window.confirm(email + " 회원의 로그인 계정을 삭제하시겠습니까?\\n\\n앱 로그인과 서비스 이용은 즉시 차단됩니다.\\n투자 데이터와 기존 리포트는 서버에 보존되지만, 새 계정을 만들어도 자동으로 연결되지는 않습니다.")) return;
        button.disabled = true;
        const response = await fetch("/api/admin/members/" + encodeURIComponent(button.dataset.id), {
            method: "DELETE", headers: {"Authorization": "Bearer " + accessToken},
        });
        if (response.ok) await loadAdminPanel(accessToken);
        else button.disabled = false;
        return;
    }
    const currentlyActive = button.dataset.active === "true";
    button.disabled = true;
    const response = await fetch("/api/admin/members/" + encodeURIComponent(button.dataset.id) + "/access", {
        method: "PUT",
        headers: {"Authorization": "Bearer " + accessToken, "Content-Type": "application/json"},
        body: JSON.stringify({active: !currentlyActive}),
    });
    if (response.ok) await loadAdminPanel(accessToken);
    else button.disabled = false;
});

const morningReportSettingsForm = document.getElementById("morning-report-settings-form");
const morningReportEnabled = document.getElementById("morning-report-enabled");
const morningReportTime = document.getElementById("morning-report-time");
const morningReportNewsEnabled = document.getElementById("morning-report-news-enabled");
const morningReportSettingsMessage = document.getElementById("morning-report-settings-message");

async function loadMorningReportSettings(accessToken) {
    const response = await fetch("/api/morning-report/settings", {
        headers: {"Authorization": "Bearer " + accessToken},
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "모닝 리포트 설정을 불러오지 못했습니다.");
    morningReportEnabled.checked = Boolean(data.morning_report_enabled);
    morningReportTime.value = data.morning_report_time || "07:30";
    morningReportNewsEnabled.checked = Boolean(data.news_enabled);
}

morningReportSettingsForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const accessToken = localStorage.getItem("access_token") || sessionStorage.getItem("access_token");
    if (!accessToken) return;
    try {
        const response = await fetch("/api/morning-report/settings", {
            method: "PUT",
            headers: {
                "Authorization": "Bearer " + accessToken,
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                morning_report_enabled: morningReportEnabled.checked,
                morning_report_time: morningReportTime.value,
                news_enabled: morningReportNewsEnabled.checked,
                ai_advice_enabled: document.getElementById("ai-advice-enabled").checked,
            }),
        });
        const data = await response.json();
        if (!response.ok) {
            const detail = Array.isArray(data.detail)
                ? data.detail.map(item => item.msg || JSON.stringify(item)).join(" / ")
                : data.detail;
            throw new Error(detail || "모닝 리포트 설정을 저장하지 못했습니다.");
        }
        morningReportSettingsMessage.textContent = "저장되었습니다.";
    } catch (error) {
        morningReportSettingsMessage.textContent = error.message || "모닝 리포트 설정을 저장하지 못했습니다.";
    }
});

const kakaoStatus = document.getElementById("kakao-status");
const kakaoConnectButton = document.getElementById("kakao-connect-button");\nconst kakaoTestButton = document.getElementById("kakao-test-button");\nconst kakaoDisconnectButton = document.getElementById("kakao-disconnect-button");

async function loadKakaoStatus(accessToken) {
    const response = await fetch("/api/kakao/status", {
        headers: {"Authorization": "Bearer " + accessToken},
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "카카오 연결 상태를 확인하지 못했습니다.");
    kakaoStatus.textContent = data.connected
        ? "카카오톡 연결 완료"
        : data.needs_reconnect
            ? "카카오톡 메시지 전송 권한 확인이 필요합니다. 다시 연결해주세요."
            : "카카오톡이 아직 연결되지 않았습니다.";
    kakaoStatus.className = data.connected
        ? "status-box success"
        : data.needs_reconnect
            ? "status-box error"
            : "status-box";
    kakaoConnectButton.textContent = data.connected || data.needs_reconnect
        ? "카카오톡 다시 연결"
        : "카카오톡 연결";
    kakaoTestButton.style.display = data.connected ? "block" : "none";
    kakaoDisconnectButton.style.display = data.connected || data.needs_reconnect ? "block" : "none";
}

kakaoTestButton.addEventListener("click", async () => {
    const accessToken = localStorage.getItem("access_token") || sessionStorage.getItem("access_token");
    if (!accessToken) return;
    kakaoTestButton.disabled = true;
    try {
        const response = await fetch("/api/kakao/test", {
            method: "POST",
            headers: {"Authorization": "Bearer " + accessToken},
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "테스트 메시지를 보내지 못했습니다.");
        kakaoStatus.textContent = data.message || "카카오톡 테스트 메시지를 보냈습니다.";
        kakaoStatus.className = "status-box success";
    } catch (error) {
        kakaoStatus.textContent = error.message || "테스트 메시지를 보내지 못했습니다.";
        kakaoStatus.className = "status-box error";
    } finally {
        kakaoTestButton.disabled = false;
    }
});

kakaoDisconnectButton.addEventListener("click", async () => {
    const accessToken = localStorage.getItem("access_token") || sessionStorage.getItem("access_token");
    if (!accessToken) return;
    kakaoDisconnectButton.disabled = true;
    try {
        const response = await fetch("/api/kakao/disconnect", {
            method: "DELETE",
            headers: {"Authorization": "Bearer " + accessToken},
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "카카오 연결을 해제하지 못했습니다.");
        await loadKakaoStatus(accessToken);
    } catch (error) {
        kakaoStatus.textContent = error.message || "카카오 연결을 해제하지 못했습니다.";
        kakaoStatus.className = "status-box error";
    } finally {
        kakaoDisconnectButton.disabled = false;
    }
});

kakaoConnectButton.addEventListener("click", async () => {
    const accessToken = localStorage.getItem("access_token") || sessionStorage.getItem("access_token");
    if (!accessToken) return;
    kakaoConnectButton.disabled = true;
    try {
        const response = await fetch("/api/kakao/connect", {
            headers: {"Authorization": "Bearer " + accessToken},
        });
        const data = await response.json();
        if (!response.ok || !data.authorization_url) {
            throw new Error(data.detail || "카카오 연결을 시작하지 못했습니다.");
        }
        window.location.assign(data.authorization_url);
    } catch (error) {
        kakaoStatus.textContent = error.message || "카카오 연결을 시작하지 못했습니다.";
        kakaoStatus.className = "status-box error";
        kakaoConnectButton.disabled = false;
    }
});

const reportRequested =
    new URLSearchParams(window.location.search).get("view") === "report";

async function showPrivateReport(accessToken) {
    const reportSection = document.getElementById("report-section");
    const reportFrame = document.getElementById("report-frame");
    const reportMessage = document.getElementById("report-message");
    reportSection.style.display = "block";
    try {
        const response = await fetch("/api/reports/latest", {
            headers: {"Authorization": "Bearer " + accessToken},
        });
        if (!response.ok) {
            let detail = "모닝 리포트를 불러오지 못했습니다.";
            try { detail = (await response.json()).detail || detail; } catch (error) {}
            throw new Error(detail);
        }
        reportFrame.srcdoc = await response.text();
        reportMessage.style.display = "none";
        reportFrame.style.display = "block";
    } catch (error) {
        reportMessage.textContent = error.message || "모닝 리포트를 불러오지 못했습니다.";
        reportMessage.className = "status-box error";
    }
}

let storedSessionDetected = false;

try {
    storedSessionDetected = Boolean(
        localStorage.getItem("access_token")
        || localStorage.getItem("refresh_token")
    );
} catch (error) {
    storedSessionDetected = false;
}

if (storedSessionDetected) {
    loginCard.style.display = "none";
    bootScreen.style.display = "flex";
}


function formatMoney(
    value,
    currency = "KRW"
) {
    const number =
        Number(value || 0);

    const cleanCurrency =
        String(
            currency || "KRW"
        ).toUpperCase();

    if (cleanCurrency === "USD") {
        return new Intl.NumberFormat(
            "en-US",
            {
                style: "currency",
                currency: "USD",
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
            }
        ).format(number);
    }

    return new Intl.NumberFormat(
        "ko-KR",
        {
            style: "currency",
            currency: "KRW",
            maximumFractionDigits: 0,
        }
    ).format(number);
}


function getAccountCurrency(account) {
    return String(
        account?.currency || "KRW"
    ).toUpperCase();
}


function formatNumber(value) {
    return new Intl.NumberFormat(
        "ko-KR",
        {
            maximumFractionDigits: 6,
        }
    ).format(
        Number(value || 0)
    );
}

function renderAssetChart(
    container,
    chartData
) {
    container.innerHTML = "";


    const allPrices =
        Array.isArray(
            chartData.prices
        )
            ? chartData.prices
            : [];


    const allTransactions =
        Array.isArray(
            chartData.transactions
        )
            ? chartData.transactions
            : [];


    const currency =
        String(
            chartData.currency
            || "KRW"
        ).toUpperCase();


    const validPrices =
        allPrices.filter(
            (item) => {

                const close =
                    Number(
                        item.close
                    );

                return (
                    item.date
                    && Number.isFinite(
                        close
                    )
                    && close > 0
                );
            }
        );


    if (validPrices.length === 0) {

        const empty =
            document.createElement(
                "div"
            );

        empty.className =
            "asset-chart-empty";

        empty.textContent =
            "표시할 가격 데이터가 없습니다.";

        container.appendChild(
            empty
        );

        return;
    }


    function parseDate(
        value
    ) {
        const date =
            new Date(
                String(value)
                + "T00:00:00"
            );

        if (
            Number.isNaN(
                date.getTime()
            )
        ) {
            return null;
        }

        return date;
    }


    function getPeriodStartDate(
        periodKey,
        latestDate
    ) {
        if (
            periodKey === "ALL"
        ) {
            return null;
        }


        const startDate =
            new Date(
                latestDate.getTime()
            );


        if (
            periodKey === "1M"
        ) {
            startDate.setMonth(
                startDate.getMonth()
                - 1
            );

            return startDate;
        }


        if (
            periodKey === "3M"
        ) {
            startDate.setMonth(
                startDate.getMonth()
                - 3
            );

            return startDate;
        }


        if (
            periodKey === "6M"
        ) {
            startDate.setMonth(
                startDate.getMonth()
                - 6
            );

            return startDate;
        }


        if (
            periodKey === "1Y"
        ) {
            startDate.setFullYear(
                startDate.getFullYear()
                - 1
            );

            return startDate;
        }


        return null;
    }


    const latestDate =
        parseDate(
            validPrices[
                validPrices.length - 1
            ].date
        );


    if (!latestDate) {

        const empty =
            document.createElement(
                "div"
            );

        empty.className =
            "asset-chart-empty";

        empty.textContent =
            "가격 날짜를 확인할 수 없습니다.";

        container.appendChild(
            empty
        );

        return;
    }


    const periodButtons =
        document.createElement(
            "div"
        );

    periodButtons.className =
        "asset-chart-period-buttons";


    const periods = [
        {
            key: "1M",
            label: "1개월",
        },
        {
            key: "3M",
            label: "3개월",
        },
        {
            key: "6M",
            label: "6개월",
        },
        {
            key: "1Y",
            label: "1년",
        },
        {
            key: "ALL",
            label: "전체",
        },
    ];


    let selectedPeriod =
        "1Y";


    const buttonMap =
        new Map();


    for (
        const period
        of periods
    ) {

        const button =
            document.createElement(
                "button"
            );

        button.type =
            "button";

        button.className =
            "asset-chart-period-button";

        button.textContent =
            period.label;


        if (
            period.key
            === selectedPeriod
        ) {
            button.classList.add(
                "active"
            );
        }


        buttonMap.set(
            period.key,
            button
        );


        periodButtons.appendChild(
            button
        );
    }


    container.appendChild(
        periodButtons
    );


    const chartBody =
        document.createElement(
            "div"
        );

    container.appendChild(
        chartBody
    );


    function drawChart(
        periodKey
    ) {
        chartBody.innerHTML =
            "";


        const startDate =
            getPeriodStartDate(
                periodKey,
                latestDate
            );


        const prices =
            validPrices.filter(
                (item) => {

                    if (!startDate) {
                        return true;
                    }


                    const itemDate =
                        parseDate(
                            item.date
                        );


                    if (!itemDate) {
                        return false;
                    }


                    return (
                        itemDate
                        >= startDate
                    );
                }
            );


        if (
            prices.length === 0
        ) {

            const empty =
                document.createElement(
                    "div"
                );

            empty.className =
                "asset-chart-empty";

            empty.textContent =
                "선택한 기간의 가격 데이터가 없습니다.";

            chartBody.appendChild(
                empty
            );

            return;
        }


        const firstPriceDate =
            parseDate(
                prices[0].date
            );


        const lastPriceDate =
            parseDate(
                prices[
                    prices.length - 1
                ].date
            );


        const transactions =
            allTransactions.filter(
                (item) => {

                    const transactionDate =
                        parseDate(
                            item.date
                        );


                    if (
                        !transactionDate
                        || !firstPriceDate
                        || !lastPriceDate
                    ) {
                        return false;
                    }


                    return (
                        transactionDate
                        >= firstPriceDate
                        && transactionDate
                        <= lastPriceDate
                    );
                }
            );


        const width =
            600;

        const height =
            230;

        const paddingLeft =
            58;

        const paddingRight =
            18;

        const paddingTop =
            18;

        const paddingBottom =
            34;


        const plotWidth =
            width
            - paddingLeft
            - paddingRight;

        const plotHeight =
            height
            - paddingTop
            - paddingBottom;


        const closeValues =
            prices.map(
                (item) =>
                    Number(
                        item.close
                    )
            );


        const transactionPrices =
            transactions
                .map(
                    (item) =>
                        Number(
                            item.price
                        )
                )
                .filter(
                    (value) =>
                        Number.isFinite(
                            value
                        )
                        && value > 0
                );


        const allValues = [
            ...closeValues,
            ...transactionPrices,
        ];


        let minimumPrice =
            Math.min(
                ...allValues
            );

        let maximumPrice =
            Math.max(
                ...allValues
            );


        if (
            minimumPrice
            === maximumPrice
        ) {

            const margin =
                minimumPrice > 0
                    ? minimumPrice
                        * 0.02
                    : 1;

            minimumPrice -=
                margin;

            maximumPrice +=
                margin;
        }


        const priceRange =
            maximumPrice
            - minimumPrice;


        const verticalMargin =
            priceRange * 0.08;


        minimumPrice -=
            verticalMargin;

        maximumPrice +=
            verticalMargin;


        const adjustedRange =
            maximumPrice
            - minimumPrice;


        function getX(
            index
        ) {

            if (
                prices.length === 1
            ) {
                return (
                    paddingLeft
                    + plotWidth / 2
                );
            }


            return (
                paddingLeft
                + (
                    index
                    / (
                        prices.length
                        - 1
                    )
                )
                * plotWidth
            );
        }


        function getY(
            price
        ) {

            return (
                paddingTop
                + (
                    (
                        maximumPrice
                        - price
                    )
                    / adjustedRange
                )
                * plotHeight
            );
        }


        function createSvgElement(
            tagName
        ) {

            return (
                document.createElementNS(
                    "http://www.w3.org/2000/svg",
                    tagName
                )
            );
        }


        const summary =
            document.createElement(
                "div"
            );

        summary.className =
            "asset-chart-summary";


        const latestPrice =
            closeValues[
                closeValues.length - 1
            ];


        const latestPriceElement =
            document.createElement(
                "div"
            );

        latestPriceElement.className =
            "asset-chart-price";

        latestPriceElement.textContent =
            formatMoney(
                latestPrice,
                currency
            );


        const period =
            document.createElement(
                "div"
            );

        period.className =
            "asset-chart-period";

        period.textContent =
            prices.length
            + "개 가격 데이터";


        summary.appendChild(
            latestPriceElement
        );

        summary.appendChild(
            period
        );

        chartBody.appendChild(
            summary
        );


        const chartContainer =
            document.createElement(
                "div"
            );

        chartContainer.className =
            "asset-chart-container";


        const svg =
            createSvgElement(
                "svg"
            );

        svg.setAttribute(
            "viewBox",
            "0 0 "
            + width
            + " "
            + height
        );

        svg.setAttribute(
            "preserveAspectRatio",
            "none"
        );

        svg.classList.add(
            "asset-chart-svg"
        );


        const gridCount =
            4;


        for (
            let index = 0;
            index <= gridCount;
            index += 1
        ) {

            const ratio =
                index
                / gridCount;


            const y =
                paddingTop
                + ratio
                * plotHeight;


            const gridLine =
                createSvgElement(
                    "line"
                );

            gridLine.setAttribute(
                "x1",
                paddingLeft
            );

            gridLine.setAttribute(
                "x2",
                width
                - paddingRight
            );

            gridLine.setAttribute(
                "y1",
                y
            );

            gridLine.setAttribute(
                "y2",
                y
            );

            gridLine.setAttribute(
                "stroke",
                "#eceff3"
            );

            gridLine.setAttribute(
                "stroke-width",
                "1"
            );


            svg.appendChild(
                gridLine
            );


            const gridPrice =
                maximumPrice
                - ratio
                * adjustedRange;


            const priceLabel =
                createSvgElement(
                    "text"
                );

            priceLabel.setAttribute(
                "x",
                paddingLeft - 7
            );

            priceLabel.setAttribute(
                "y",
                y + 4
            );

            priceLabel.setAttribute(
                "text-anchor",
                "end"
            );

            priceLabel.setAttribute(
                "font-size",
                "10"
            );

            priceLabel.setAttribute(
                "fill",
                "#8a8f98"
            );


            priceLabel.textContent =
                currency === "USD"
                    ? gridPrice.toFixed(
                        2
                    )
                    : Math.round(
                        gridPrice
                    ).toLocaleString(
                        "ko-KR"
                    );


            svg.appendChild(
                priceLabel
            );
        }


        const points =
            prices.map(
                (
                    item,
                    index
                ) => {

                    return (
                        getX(
                            index
                        )
                        + ","
                        + getY(
                            Number(
                                item.close
                            )
                        )
                    );
                }
            );


        const priceLine =
            createSvgElement(
                "polyline"
            );

        priceLine.setAttribute(
            "points",
            points.join(
                " "
            )
        );

        priceLine.setAttribute(
            "fill",
            "none"
        );

        priceLine.setAttribute(
            "stroke",
            "#202124"
        );

        priceLine.setAttribute(
            "stroke-width",
            "2.5"
        );

        priceLine.setAttribute(
            "stroke-linejoin",
            "round"
        );

        priceLine.setAttribute(
            "stroke-linecap",
            "round"
        );

        priceLine.setAttribute(
            "vector-effect",
            "non-scaling-stroke"
        );


        svg.appendChild(
            priceLine
        );


        const dateIndexes = [
            0,
            Math.floor(
                (
                    prices.length
                    - 1
                )
                / 2
            ),
            prices.length - 1,
        ];


        const uniqueDateIndexes = [
            ...new Set(
                dateIndexes
            ),
        ];


        for (
            const index
            of uniqueDateIndexes
        ) {

            const item =
                prices[index];


            if (!item) {
                continue;
            }


            const dateLabel =
                createSvgElement(
                    "text"
                );


            let anchor =
                "middle";


            if (
                index === 0
            ) {
                anchor =
                    "start";
            }


            if (
                index
                === prices.length - 1
            ) {
                anchor =
                    "end";
            }


            dateLabel.setAttribute(
                "x",
                getX(
                    index
                )
            );

            dateLabel.setAttribute(
                "y",
                height - 9
            );

            dateLabel.setAttribute(
                "text-anchor",
                anchor
            );

            dateLabel.setAttribute(
                "font-size",
                "10"
            );

            dateLabel.setAttribute(
                "fill",
                "#8a8f98"
            );


            const date =
                parseDate(
                    item.date
                );


            if (!date) {
                dateLabel.textContent =
                    item.date;
            } else {
                dateLabel.textContent =
                    (
                        date.getMonth()
                        + 1
                    )
                    + "/"
                    + date.getDate();
            }


            svg.appendChild(
                dateLabel
            );
        }


        const tooltip =
            document.createElement(
                "div"
            );

        tooltip.className =
            "asset-chart-tooltip";


        function findNearestPriceIndex(
            transactionDate
        ) {

            const targetDate =
                parseDate(
                    transactionDate
                );


            if (!targetDate) {
                return 0;
            }


            const targetTime =
                targetDate.getTime();


            let nearestIndex =
                0;

            let nearestDifference =
                Infinity;


            for (
                let index = 0;
                index < prices.length;
                index += 1
            ) {

                const priceDate =
                    parseDate(
                        prices[index]
                            .date
                    );


                if (!priceDate) {
                    continue;
                }


                const difference =
                    Math.abs(
                        priceDate.getTime()
                        - targetTime
                    );


                if (
                    difference
                    < nearestDifference
                ) {

                    nearestDifference =
                        difference;

                    nearestIndex =
                        index;
                }
            }


            return nearestIndex;
        }


        const transactionMarkerCounts = new Map();

        for (
            const transaction
            of transactions
        ) {

            const transactionPrice =
                Number(
                    transaction.price
                );


            if (
                !Number.isFinite(
                    transactionPrice
                )
                || transactionPrice <= 0
                || !transaction.date
            ) {
                continue;
            }


            const nearestIndex =
                findNearestPriceIndex(
                    transaction.date
                );


            const baseX =
                getX(
                    nearestIndex
                );

            const markerGroupKey =
                String(transaction.date)
                + "|"
                + String(transaction.type || "").toUpperCase();
            const markerGroupIndex =
                transactionMarkerCounts.get(markerGroupKey) || 0;
            transactionMarkerCounts.set(markerGroupKey, markerGroupIndex + 1);

            const markerOffsetStep = 11;
            const markerOffsetDirection =
                markerGroupIndex === 0 ? 0 : (markerGroupIndex % 2 === 1 ? 1 : -1);
            const markerOffsetLevel =
                markerGroupIndex === 0 ? 0 : Math.ceil(markerGroupIndex / 2);

            const x =
                Math.max(
                    paddingLeft + 9,
                    Math.min(
                        width - paddingRight - 9,
                        baseX + markerOffsetDirection * markerOffsetLevel * markerOffsetStep
                    )
                );

            const y =
                getY(
                    transactionPrice
                );


            const transactionType =
                String(
                    transaction.type
                    || ""
                ).toUpperCase();


            const marker =
                createSvgElement(
                    "polygon"
                );


            /*
            삼각형의 꼭짓점이 실제 체결가격을 가리키도록 합니다.

            매수:
            가격 아래에서 위를 향하는 ▲

            매도:
            가격 위에서 아래를 향하는 ▼
            */

            const markerWidth =
                8;

            const markerHeight =
                10;

            const markerGap =
                3;


            let markerPoints =
                "";


            if (
                transactionType
                === "SELL"
            ) {

                /*
                매도 ▼

                실제 체결가격 위치(y)에서
                위쪽으로 삼각형을 배치하고,
                아래쪽 꼭짓점이 가격을 가리킵니다.
                */

                const tipY =
                    y - markerGap;


                markerPoints =
                    x
                    + ","
                    + tipY
                    + " "
                    + (
                        x
                        - markerWidth
                    )
                    + ","
                    + (
                        tipY
                        - markerHeight
                    )
                    + " "
                    + (
                        x
                        + markerWidth
                    )
                    + ","
                    + (
                        tipY
                        - markerHeight
                    );


                marker.setAttribute(
                    "fill",
                    "#137333"
                );


            } else {

                /*
                매수 ▲

                실제 체결가격 위치(y)에서
                아래쪽으로 삼각형을 배치하고,
                위쪽 꼭짓점이 가격을 가리킵니다.
                */

                const tipY =
                    y + markerGap;


                markerPoints =
                    x
                    + ","
                    + tipY
                    + " "
                    + (
                        x
                        - markerWidth
                    )
                    + ","
                    + (
                        tipY
                        + markerHeight
                    )
                    + " "
                    + (
                        x
                        + markerWidth
                    )
                    + ","
                    + (
                        tipY
                        + markerHeight
                    );


                marker.setAttribute(
                    "fill",
                    "#b3261e"
                );
            }


            marker.setAttribute(
                "points",
                markerPoints
            );


            marker.setAttribute(
                "stroke",
                "#ffffff"
            );


            marker.setAttribute(
                "stroke-width",
                "1.5"
            );


            marker.setAttribute(
                "stroke-linejoin",
                "round"
            );


            marker.setAttribute(
                "vector-effect",
                "non-scaling-stroke"
            );


            marker.style.cursor =
                "pointer";


            marker.addEventListener(
                "click",
                (event) => {

                    event.stopPropagation();


                    const typeText =
                        transactionType
                        === "SELL"
                            ? "매도"
                            : "매수";


                    tooltip.innerHTML =
                        "<strong>"
                        + transaction.date
                        + " · "
                        + typeText
                        + "</strong>"
                        + "<br>"
                        + "체결가격 "
                        + formatMoney(
                            transaction.price,
                            currency
                        )
                        + "<br>"
                        + "수량 "
                        + formatNumber(
                            transaction.quantity
                        )
                        + "주"
                        + "<br>"
                        + "수수료 "
                        + formatMoney(
                            transaction.fee,
                            currency
                        )
                        + " · 세금 "
                        + formatMoney(
                            transaction.tax,
                            currency
                        );


                    tooltip.classList.add(
                        "visible"
                    );
                }
            );


            svg.appendChild(
                marker
            );
        }


        chartContainer.appendChild(
            svg
        );

        const crosshairGroup =
            createSvgElement(
                "g"
            );

        crosshairGroup.classList.add(
            "asset-chart-crosshair"
        );

        crosshairGroup.style.display =
            "none";


        const crosshairLine =
            createSvgElement(
                "line"
            );

        crosshairLine.classList.add(
            "asset-chart-touch-line"
        );

        crosshairLine.setAttribute(
            "y1",
            paddingTop
        );

        crosshairLine.setAttribute(
            "y2",
            paddingTop
            + plotHeight
        );


        const crosshairPoint =
            createSvgElement(
                "circle"
            );

        crosshairPoint.classList.add(
            "asset-chart-touch-point"
        );

        crosshairPoint.setAttribute(
            "r",
            "5"
        );


        crosshairGroup.appendChild(
            crosshairLine
        );

        crosshairGroup.appendChild(
            crosshairPoint
        );

        svg.appendChild(
            crosshairGroup
        );


        const touchLabel =
            document.createElement(
                "div"
            );

        touchLabel.className =
            "asset-chart-touch-label";

        chartContainer.appendChild(
            touchLabel
        );


        function showPriceAtPointer(
            event
        ) {
            const rect =
                svg.getBoundingClientRect();


            if (
                rect.width <= 0
                || prices.length === 0
            ) {
                return;
            }


            const pointerX =
                event.clientX
                - rect.left;


            const scaleX =
                width
                / rect.width;


            const svgX =
                pointerX
                * scaleX;


            const clampedX =
                Math.max(
                    paddingLeft,
                    Math.min(
                        width
                        - paddingRight,
                        svgX
                    )
                );


            let index = 0;


            if (
                prices.length > 1
            ) {
                const ratio =
                    (
                        clampedX
                        - paddingLeft
                    )
                    / plotWidth;


                index =
                    Math.round(
                        ratio
                        * (
                            prices.length
                            - 1
                        )
                    );


                index =
                    Math.max(
                        0,
                        Math.min(
                            prices.length
                            - 1,
                            index
                        )
                    );
            }


            const item =
                prices[index];


            if (!item) {
                return;
            }


            const close =
                Number(
                    item.close
                );


            if (
                !Number.isFinite(
                    close
                )
            ) {
                return;
            }


            const x =
                getX(
                    index
                );

            const y =
                getY(
                    close
                );


            crosshairLine.setAttribute(
                "x1",
                x
            );

            crosshairLine.setAttribute(
                "x2",
                x
            );

            crosshairPoint.setAttribute(
                "cx",
                x
            );

            crosshairPoint.setAttribute(
                "cy",
                y
            );


            crosshairGroup.style.display =
                "";


            touchLabel.innerHTML =
                "<strong>"
                + item.date
                + "</strong>"
                + "<br>"
                + "종가 "
                + formatMoney(
                    close,
                    currency
                );


            const screenX =
                (
                    x
                    / width
                )
                * rect.width;


            const minimumLabelX =
                55;

            const maximumLabelX =
                rect.width - 55;


            const labelX =
                Math.max(
                    minimumLabelX,
                    Math.min(
                        maximumLabelX,
                        screenX
                    )
                );


            touchLabel.style.left =
                labelX
                + "px";

            touchLabel.style.top =
                "8px";

            touchLabel.classList.add(
                "visible"
            );
        }


        function hidePricePointer() {
            crosshairGroup.style.display =
                "none";

            touchLabel.classList.remove(
                "visible"
            );
        }


        svg.addEventListener(
            "pointerdown",
            (event) => {

                showPriceAtPointer(
                    event
                );
            }
        );


        svg.addEventListener(
            "pointermove",
            (event) => {

                if (
                    event.pointerType
                    === "mouse"
                    && event.buttons === 0
                ) {
                    return;
                }


                showPriceAtPointer(
                    event
                );
            }
        );


        svg.addEventListener(
            "pointerleave",
            () => {

                hidePricePointer();
            }
        );


        svg.addEventListener(
            "pointerup",
            () => {

                /*
                 * 손가락을 뗀 뒤에도
                 * 마지막 선택 가격을 유지합니다.
                 */
            }
        );       

        chartBody.appendChild(
            chartContainer
        );


        const legend =
            document.createElement(
                "div"
            );

        legend.className =
            "asset-chart-legend";


        const buyLegend =
            document.createElement(
                "div"
            );

        buyLegend.className =
            "asset-chart-legend-item";

        buyLegend.innerHTML =
            '<span class="asset-chart-marker buy-marker"></span>'
            + "매수 BUY ▲";


        const sellLegend =
            document.createElement(
                "div"
            );

        sellLegend.className =
            "asset-chart-legend-item";

        sellLegend.innerHTML =
            '<span class="asset-chart-marker sell-marker"></span>'
            + "매도 SELL ▼";


        legend.appendChild(
            buyLegend
        );

        legend.appendChild(
            sellLegend
        );

        chartBody.appendChild(
            legend
        );

        chartBody.appendChild(
            tooltip
        );
    }


    for (
        const period
        of periods
    ) {

        const button =
            buttonMap.get(
                period.key
            );


        if (!button) {
            continue;
        }


        button.addEventListener(
            "click",
            (event) => {

                event.stopPropagation();


                selectedPeriod =
                    period.key;


                for (
                    const [
                        key,
                        periodButton,
                    ]
                    of buttonMap
                ) {

                    periodButton
                        .classList
                        .toggle(
                            "active",
                            key
                            === selectedPeriod
                        );
                }


                drawChart(
                    selectedPeriod
                );
            }
        );
    }


    drawChart(
        selectedPeriod
    );
}


function formatPercent(value) {
    const number =
        Number(value || 0);

    const percent =
        Math.abs(number) <= 1
        ? number * 100
        : number;

    return new Intl.NumberFormat(
        "ko-KR",
        {
            maximumFractionDigits: 2,
        }
    ).format(percent) + "%";
}


function todayString() {
    const date = new Date();

    const year =
        date.getFullYear();

    const month =
        String(
            date.getMonth() + 1
        ).padStart(2, "0");

    const day =
        String(
            date.getDate()
        ).padStart(2, "0");

    return (
        year
        + "-"
        + month
        + "-"
        + day
    );
}


function accountTypeText(value) {

    const map = {
        retirement: "퇴직연금",
        pension: "연금계좌",
        isa: "ISA",
        brokerage: "일반 증권계좌",
    };

    return map[value] || value || "-";
}


function marketScopeText(value) {

    const map = {
        KR: "한국",
        US: "미국",
        GLOBAL: "글로벌",
    };

    return map[value] || value || "-";
}


function strategyTypeText(value) {

    const map = {
        allocation: "자산배분",
        trading: "트레이딩",
        mixed: "혼합",
    };

    return map[value] || value || "-";
}


function contributionTypeText(value) {

    const map = {
        none: "정기 납입 없음",
        monthly: "매월",
        yearly: "연 1회",
        irregular: "비정기",
    };

    return map[value] || value || "-";
}


async function apiRequest(
    url,
    accessToken,
    options = {}
) {
    const headers = {
        ...(options.headers || {}),
        "Authorization":
            "Bearer " + accessToken,
    };


    let response;

    try {

        response =
            await fetch(
                url,
                {
                    ...options,
                    headers: headers,
                }
            );

    } catch (error) {

        console.error(
            "API fetch 오류:",
            url,
            error
        );

        throw new Error(
            "API 요청 실패: "
            + (
                error.message
                || "네트워크 오류"
            )
        );
    }


    const responseText =
        await response.text();


    let data = null;

    if (responseText) {

        try {

            data =
                JSON.parse(
                    responseText
                );

        } catch (error) {

            console.error(
                "API JSON 해석 오류:",
                {
                    url: url,
                    status:
                        response.status,
                    contentType:
                        response.headers.get(
                            "content-type"
                        ),
                    responseText:
                        responseText,
                    error:
                        error,
                }
            );

            throw new Error(
                "서버 응답 형식 오류"
                + " · HTTP "
                + response.status
                + " · "
                + responseText.slice(
                    0,
                    120
                )
            );
        }
    }


    if (!response.ok) {

        const detail =
            data
            && data.detail
            ? data.detail
            : (
                "HTTP "
                + response.status
                + " 요청 오류"
            );

        throw new Error(
            detail
        );
    }


    return data;
}


async function verifyUser(
    accessToken
) {
    return await apiRequest(
        "/api/me",
        accessToken
    );
}


async function loadAccounts(
    accessToken
) {
    const data =
        await apiRequest(
            "/api/accounts",
            accessToken
        );

    return data.accounts || [];
}


async function saveAccount(
    accessToken,
    accountId,
    payload
) {
    return await apiRequest(
        "/api/accounts/"
        + accountId,
        accessToken,
        {
            method: "PUT",

            headers: {
                "Content-Type":
                    "application/json",
            },

            body:
                JSON.stringify(payload),
        }
    );
}


async function loadAccountTargets(
    accessToken,
    accountId
) {
    const data =
        await apiRequest(
            "/api/accounts/"
            + accountId
            + "/targets",
            accessToken
        );

    return data.targets || [];
}


async function loadTransactions(
    accessToken,
    accountId
) {
    const data =
        await apiRequest(
            "/api/accounts/"
            + accountId
            + "/transactions",
            accessToken
        );

    return data.transactions || [];
}


async function loadPositions(
    accessToken,
    accountId
) {
    const data =
        await apiRequest(
            "/api/accounts/"
            + accountId
            + "/positions",
            accessToken
        );

    return {
        summary:
            data.summary || null,

        positions:
            data.positions || [],

        currency:
            data.currency || "KRW",

        total_current_value:
            Number(
                data.total_current_value
                || 0
            )
    };
}

async function loadAssetChart(
    accessToken,
    accountId,
    ticker,
    options = {}
) {
    const params =
        new URLSearchParams();


    if (options.startDate) {
        params.set(
            "start_date",
            options.startDate
        );
    }


    if (options.endDate) {
        params.set(
            "end_date",
            options.endDate
        );
    }


    if (options.limit) {
        params.set(
            "limit",
            String(
                options.limit
            )
        );
    }


    let path =
        "/api/accounts/"
        + encodeURIComponent(
            accountId
        )
        + "/assets/"
        + encodeURIComponent(
            ticker
        )
        + "/chart";


    const queryString =
        params.toString();


    if (queryString) {
        path +=
            "?"
            + queryString;
    }


    const data =
        await apiRequest(
            path,
            accessToken
        );


    return {
        account_id:
            data.account_id,

        account_name:
            data.account_name || "",

        account_currency:
            data.account_currency || "KRW",

        ticker:
            data.ticker || ticker,

        name:
            data.name || ticker,

        currency:
            data.currency
            || data.account_currency
            || "KRW",

        market:
            data.market || "",

        price_count:
            Number(
                data.price_count
                || 0
            ),

        transaction_count:
            Number(
                data.transaction_count
                || 0
            ),

        prices:
            Array.isArray(
                data.prices
            )
                ? data.prices
                : [],

        transactions:
            Array.isArray(
                data.transactions
            )
                ? data.transactions
                : [],
    };
}


async function lookupUsAsset(
    accessToken,
    ticker
) {
    const cleanTicker =
        String(
            ticker || ""
        )
        .trim()
        .toUpperCase();

    if (!cleanTicker) {
        throw new Error(
            "미국 종목 티커를 입력해주세요."
        );
    }

    return await apiRequest(
        "/api/assets/us/"
        + encodeURIComponent(
            cleanTicker
        ),
        accessToken
    );
}

async function searchRegisteredAssets(
    accessToken,
    keyword = ""
) {
    const data =
        await apiRequest(
            "/api/assets?q="
            + encodeURIComponent(
                String(
                    keyword || ""
                ).trim()
            )
            + "&limit=100",
            accessToken
        );

    return data.assets || [];
}


async function loadInvestmentProfile(
    accessToken
) {
    const data =
        await apiRequest(
            "/api/investment-profile",
            accessToken
        );

    return data.profile;
}


async function saveInvestmentProfile(
    accessToken,
    payload
) {
    return await apiRequest(
        "/api/investment-profile",
        accessToken,
        {
            method: "PUT",

            headers: {
                "Content-Type":
                    "application/json",
            },

            body:
                JSON.stringify(payload),
        }
    );
}


function createDetail(text) {

    const element =
        document.createElement(
            "div"
        );

    element.className =
        "account-detail";

    element.textContent =
        text;

    return element;
}


function renderTargets(
    container,
    targets
) {
    container.innerHTML = "";

    if (targets.length === 0) {

        const empty =
            document.createElement(
                "div"
            );

        empty.className =
            "empty";

        empty.textContent =
            "등록된 목표 종목이 없습니다.";

        container.appendChild(
            empty
        );

        return;
    }

    for (const target of targets) {

        const row =
            document.createElement(
                "div"
            );

        row.className =
            "target-row";

        const info =
            document.createElement(
                "div"
            );

        info.className =
            "target-info";

        const name =
            document.createElement(
                "div"
            );

        name.className =
            "target-name";

        name.textContent =
            target.name || "-";

        const ticker =
            document.createElement(
                "div"
            );

        ticker.className =
            "target-ticker";

        ticker.textContent =
            target.ticker || "-";

        const weight =
            document.createElement(
                "div"
            );

        weight.className =
            "target-weight";

        weight.textContent =
            formatPercent(
                target.target_weight
            );

        info.appendChild(name);
        info.appendChild(ticker);

        row.appendChild(info);
        row.appendChild(weight);

        container.appendChild(row);
    }
}

function renderAccountSummary(
    container,
    summary,
    account
) {
    container.innerHTML = "";

    if (!summary) {

        container.textContent =
            "계좌 요약을 불러올 수 없습니다.";

        container.className =
            "transaction-row error";

        return;
    }


    container.className =
        "account-summary-grid";


    const summaryCurrency =
        String(
            summary.currency
            || getAccountCurrency(
                account
            )
        )
        .trim()
        .toUpperCase();


    function appendKpi(
        label,
        value,
        tone = ""
    ) {
        const item =
            document.createElement("div");
        item.className =
            "summary-kpi";

        const itemLabel =
            document.createElement("div");
        itemLabel.className =
            "summary-kpi-label";
        itemLabel.textContent = label;

        const itemValue =
            document.createElement("div");
        itemValue.className =
            "summary-kpi-value"
            + (tone ? " " + tone : "");
        itemValue.textContent = value;

        item.appendChild(itemLabel);
        item.appendChild(itemValue);
        container.appendChild(item);
    }

    appendKpi(
        "총자산",
        formatMoney(
            summary.total_assets,
            summaryCurrency
        )
    );

    appendKpi(
        "주식평가액",
        formatMoney(
            summary.total_current_value,
            summaryCurrency
        )
    );

    appendKpi(
        "예수금",
        formatMoney(
            summary.cash_balance,
            summaryCurrency
        )
    );


    const unrealizedPnl =
        Number(
            summary.total_unrealized_pnl
            || 0
        );


    const unrealizedDetail =
        createDetail(
            "평가손익: "
            + (
                unrealizedPnl > 0
                ? "+"
                : ""
            )
            + formatMoney(
                unrealizedPnl,
                summaryCurrency
            )
        );


    if (unrealizedPnl > 0) {

        unrealizedDetail.classList.add(
            "sell"
        );
    }


    if (unrealizedPnl < 0) {

        unrealizedDetail.classList.add(
            "buy"
        );
    }


    container.appendChild(
        unrealizedDetail
    );


    const realizedPnl =
        Number(
            summary.total_realized_pnl
            || 0
        );


    container.appendChild(
        createDetail(
            "실현손익: "
            + (
                realizedPnl > 0
                ? "+"
                : ""
            )
            + formatMoney(
                realizedPnl,
                summaryCurrency
            )
        )
    );


    container.appendChild(
        createDetail(
            "배당금: "
            + formatMoney(
                summary.total_dividends,
                summaryCurrency
            )
        )
    );


    const totalPnl =
        Number(
            summary.total_pnl
            || 0
        );

    appendKpi(
        "총손익",
        (
            totalPnl > 0
            ? "+"
            : ""
        )
        + formatMoney(
            totalPnl,
            summaryCurrency
        )
        + " ("
        + (
            Number(summary.total_roi || 0) > 0
            ? "+"
            : ""
        )
        + formatPercent(summary.total_roi)
        + ")",
        totalPnl > 0
            ? "sell"
            : (totalPnl < 0 ? "buy" : "")
    );

    container.appendChild(
        createDetail(
            "현재 보유분 매수원가: "
            + formatMoney(
                summary.total_invested,
                summaryCurrency
            )
        )
    );


    container.appendChild(
        createDetail(
            "보유종목: "
            + Number(
                summary.position_count
                || 0
            )
            + "개"
        )
    );
}

function openLinkedAssetChart() {
    const params =
        new URLSearchParams(
            window.location.search
        );


    const accountId =
        String(
            params.get(
                "account"
            )
            || ""
        ).trim();


    const ticker =
        String(
            params.get(
                "ticker"
            )
            || ""
        )
        .trim()
        .toUpperCase();


    if (
        !accountId
        || !ticker
    ) {
        return false;
    }


    const rows =
        document.querySelectorAll(
            ".position-row"
        );


    let targetRow =
        null;


    for (const row of rows) {

        if (
            String(
                row.dataset.accountId
                || ""
            ) === accountId
            && String(
                row.dataset.ticker
                || ""
            ).toUpperCase()
            === ticker
        ) {
            targetRow =
                row;

            break;
        }
    }


    if (!targetRow) {
        return false;
    }


    /*
    먼저 차트를 엽니다.
    차트가 펼쳐지면서 화면 높이가 변하므로
    스크롤은 차트를 연 뒤 실행합니다.
    */

    targetRow.click();


    window.setTimeout(
        () => {

            targetRow.scrollIntoView({
                behavior:
                    "smooth",

                block:
                    "start",
            });

        },
        500
    );


    return true;
}


function renderPositions(
    container,
    positions,
    account,
    accessToken
) {
    container.innerHTML = "";

    if (positions.length === 0) {

        const empty =
            document.createElement(
                "div"
            );

        empty.className =
            "empty";

        empty.textContent =
            "보유현황이 없습니다.";

        container.appendChild(
            empty
        );

        return;
    }


    const accountCurrency =
        getAccountCurrency(
            account
        );


    for (const position of positions) {

        const assetCurrency =
            String(
                position.currency
                || accountCurrency
            ).toUpperCase();


        const row =
            document.createElement(
                "div"
            );

        row.className =
            "transaction-row position-row";

        row.setAttribute(
            "role",
            "button"
        );
        row.tabIndex = 0;
        row.setAttribute(
            "aria-label",
            (position.name || position.ticker)
            + " 상세 가격 차트 열기"
        );

        row.dataset.accountId =
            String(
                account.id
            );

        row.dataset.ticker =
            String(
                position.ticker
                || ""
            ).toUpperCase();
            
        const header =
            document.createElement(
                "div"
            );

        header.className =
            "transaction-main";


        const name =
            document.createElement(
                "div"
            );

        name.className =
            "position-name";

        name.textContent =
            position.name
            || position.ticker;


        const value =
            document.createElement(
                "div"
            );

        value.className =
            "position-value";

        value.textContent =
            formatMoney(
                position.current_value,
                assetCurrency
            );


        header.appendChild(
            name
        );

        header.appendChild(
            value
        );

        row.appendChild(
            header
        );


        row.appendChild(
            createDetail(
                position.ticker
                + " · "
                + assetCurrency
            )
        );


        row.appendChild(
            createDetail(
                "보유 "
                + formatNumber(
                    position.quantity
                )
                + "주 · 평단 "
                + formatMoney(
                    position.average_buy_price,
                    assetCurrency
                )
            )
        );


        row.appendChild(
            createDetail(
                "현재가 "
                + formatMoney(
                    position.current_price,
                    assetCurrency
                )
                + " · 평가금액 "
                + formatMoney(
                    position.current_value,
                    assetCurrency
                )
            )
        );


        if (
            assetCurrency
            !== accountCurrency
        ) {

            row.appendChild(
                createDetail(
                    "계좌 환산 평가금액 "
                    + formatMoney(
                        position
                            .account_current_value,
                        accountCurrency
                    )
                )
            );
        }


        row.appendChild(
            createDetail(
                "현재비중 "
                + formatPercent(
                    position.current_weight
                )
                + " · 목표비중 "
                + formatPercent(
                    position.target_weight
                )
            )
        );


        const pnl =
            createDetail(
                "평가손익 "
                + (
                    Number(
                        position.unrealized_pnl
                    ) > 0
                    ? "+"
                    : ""
                )
                + formatMoney(
                    position.unrealized_pnl,
                    assetCurrency
                )
                + " ("
                + (
                    Number(
                        position.unrealized_roi
                    ) > 0
                    ? "+"
                    : ""
                )
                + formatPercent(
                    position.unrealized_roi
                )
                + ")"
            );


        if (
            Number(
                position.unrealized_pnl
            ) > 0
        ) {
            pnl.classList.add(
                "sell"
            );
        }


        if (
            Number(
                position.unrealized_pnl
            ) < 0
        ) {
            pnl.classList.add(
                "buy"
            );
        }


        row.appendChild(
            pnl
        );


        const hint =
            document.createElement(
                "div"
            );

        hint.className =
            "position-chart-hint";

        hint.textContent =
            "종목을 누르면 매매 차트를 볼 수 있습니다.";

        row.appendChild(
            hint
        );


        const chartPanel =
            document.createElement(
                "div"
            );

        chartPanel.className =
            "asset-chart-panel";

        chartPanel.style.display =
            "none";


        let chartLoaded =
            false;

        let chartLoading =
            false;


        row.addEventListener(
            "click",
            async (event) => {

                if (
                    event.target.closest(
                        "button"
                    )
                    || event.target.closest(
                        "input"
                    )
                    || event.target.closest(
                        "select"
                    )
                    || event.target.closest(
                        "textarea"
                    )
                ) {
                    return;
                }


                if (
                    chartPanel.style.display
                    !== "none"
                ) {
                    chartPanel.style.display =
                        "none";

                    return;
                }


                chartPanel.style.display =
                    "block";


                if (
                    chartLoaded
                    || chartLoading
                ) {
                    return;
                }


                chartLoading =
                    true;


                chartPanel.innerHTML = "";


                const loading =
                    document.createElement(
                        "div"
                    );

                loading.className =
                    "asset-chart-loading";

                loading.textContent =
                    "차트 데이터를 불러오는 중입니다.";

                chartPanel.appendChild(
                    loading
                );


                try {

                    const chartData =
                        await loadAssetChart(
                            accessToken,
                            account.id,
                            position.ticker
                        );


                    chartPanel.innerHTML =
                        "";


                    const chartHeader =
                        document.createElement(
                            "div"
                        );

                    chartHeader.className =
                        "asset-chart-header";


                    const titleBox =
                        document.createElement(
                            "div"
                        );

                    titleBox.className =
                        "asset-chart-title";


                    const chartName =
                        document.createElement(
                            "div"
                        );

                    chartName.className =
                        "asset-chart-name";

                    chartName.textContent =
                        chartData.name
                        || position.name
                        || position.ticker;


                    const chartTicker =
                        document.createElement(
                            "div"
                        );

                    chartTicker.className =
                        "asset-chart-ticker";

                    chartTicker.textContent =
                        chartData.ticker
                        + " · "
                        + chartData.currency;


                    titleBox.appendChild(
                        chartName
                    );

                    titleBox.appendChild(
                        chartTicker
                    );


                    const closeButton =
                        document.createElement(
                            "button"
                        );

                    closeButton.type =
                        "button";

                    closeButton.className =
                        "asset-chart-close";

                    closeButton.textContent =
                        "×";


                    closeButton.addEventListener(
                        "click",
                        (closeEvent) => {

                            closeEvent
                                .stopPropagation();

                            chartPanel.style.display =
                                "none";
                        }
                    );


                    chartHeader.appendChild(
                        titleBox
                    );

                    chartHeader.appendChild(
                        closeButton
                    );

                    chartPanel.appendChild(
                        chartHeader
                    );


                    const chartContent =
                        document.createElement(
                            "div"
                        );


                    chartPanel.appendChild(
                        chartContent
                    );


                    renderAssetChart(
                        chartContent,
                        chartData
                    );

                    chartLoaded =
                        true;

                } catch (error) {

                    chartPanel.innerHTML =
                        "";


                    const errorBox =
                        document.createElement(
                            "div"
                        );

                    errorBox.className =
                        "error";

                    errorBox.textContent =
                        error.message
                        || "차트 데이터를 불러오지 못했습니다.";

                    chartPanel.appendChild(
                        errorBox
                    );

                } finally {

                    chartLoading =
                        false;
                }
            }
        );

        row.addEventListener(
            "keydown",
            (event) => {
                if (
                    event.key === "Enter"
                    || event.key === " "
                ) {
                    event.preventDefault();
                    row.click();
                }
            }
        );


        container.appendChild(
            row
        );

        container.appendChild(
            chartPanel
        );
    }
}


function renderTransactions(
    container,
    transactions,
    targets,
    account,
    accessToken,
    positionsList
) {
    container.innerHTML = "";

    if (transactions.length === 0) {

        const empty =
            document.createElement(
                "div"
            );

        empty.className =
            "empty";

        empty.textContent =
            "아직 등록된 거래가 없습니다.";

        container.appendChild(
            empty
        );

        return;
    }

    const newestFirst =
        [...transactions].reverse();

    const pageSize = 20;
    let visibleCount = Math.min(pageSize, newestFirst.length);

    const list =
        document.createElement("div");

    const controls =
        document.createElement("div");

    controls.className =
        "transaction-list-controls";

    const countLabel =
        document.createElement("div");

    countLabel.className =
        "transaction-list-count";

    const moreButton =
        document.createElement("button");

    moreButton.type = "button";
    moreButton.className = "small-button secondary-button";
    moreButton.textContent = "20건 더 보기";

    controls.appendChild(countLabel);
    controls.appendChild(moreButton);
    container.appendChild(list);
    container.appendChild(controls);

    function drawVisibleTransactions() {
        list.innerHTML = "";

        const visibleTransactions =
            newestFirst.slice(0, visibleCount);

        for (
            const transaction
            of visibleTransactions
        ) {

        const assetCurrency =
            String(
                transaction.currency
                || getAccountCurrency(account)
            ).toUpperCase();

        const assetName =
            transaction.name
            || transaction.ticker;


        const row =
            document.createElement(
                "div"
            );

        row.className =
            "transaction-row";


        const main =
            document.createElement(
                "div"
            );

        main.className =
            "transaction-main";


        const left =
            document.createElement(
                "div"
            );

        const typeText =
            transaction.transaction_type
            === "BUY"
            ? "매수"
            : "매도";

        left.textContent =
            transaction.transaction_date
            + " · "
            + assetName
            + " ("
            + transaction.ticker
            + ") · "
            + typeText;

        left.className =
            transaction.transaction_type
            === "BUY"
            ? "buy"
            : "sell";


        const amount =
            document.createElement(
                "div"
            );

        amount.textContent =
            formatMoney(
                Number(
                    transaction.quantity
                )
                * Number(
                    transaction.price
                ),
                assetCurrency
            );


        main.appendChild(left);
        main.appendChild(amount);

        row.appendChild(main);


        row.appendChild(
            createDetail(
                "수량 "
                + formatNumber(
                    transaction.quantity
                )
                + " · 체결가 "
                + formatMoney(
                    transaction.price,
                    assetCurrency
                )
                + " · 수수료 "
                + formatMoney(
                    transaction.fee,
                    assetCurrency
                )
                + " · 세금 "
                + formatMoney(
                    transaction.tax,
                    assetCurrency
                )
            )
        );


        row.appendChild(
            createDetail(
                "거래 통화: "
                + assetCurrency
            )
        );


        if (transaction.memo) {

            row.appendChild(
                createDetail(
                    "메모: "
                    + transaction.memo
                )
            );
        }


        const actions =
            document.createElement(
                "div"
            );

        actions.className =
            "transaction-actions";


        const editButton =
            document.createElement(
                "button"
            );

        editButton.type =
            "button";

        editButton.className =
            "small-button secondary-button";

        editButton.textContent =
            "수정";


        const deleteButton =
            document.createElement(
                "button"
            );

        deleteButton.type =
            "button";

        deleteButton.className =
            "small-button delete-button";

        deleteButton.textContent =
            "삭제";


        actions.appendChild(
            editButton
        );

        actions.appendChild(
            deleteButton
        );

        row.appendChild(actions);


        editButton.addEventListener(
            "click",
            () => {
                showTransactionEditor(
                    row,
                    transaction,
                    targets,
                    account,
                    accessToken,
                    container,
                    positionsList
                );
            }
        );


        deleteButton.addEventListener(
            "click",
            async () => {

                const confirmed =
                    window.confirm(
                        assetName
                        + " 거래를 삭제할까요?"
                    );

                if (!confirmed) {
                    return;
                }

                deleteButton.disabled =
                    true;

                try {

                    await apiRequest(
                        "/api/accounts/"
                        + account.id
                        + "/transactions/"
                        + transaction.id,
                        accessToken,
                        {
                            method:
                                "DELETE",
                        }
                    );

                    await refreshPortfolioData(
                        account,
                        targets,
                        accessToken,
                        container,
                        positionsList
                    );

                } catch (error) {

                    window.alert(
                        error.message
                        || "거래 삭제에 실패했습니다."
                    );

                    deleteButton.disabled =
                        false;
                }
            }
        );


        list.appendChild(row);
        }

        countLabel.textContent =
            "최근 "
            + visibleCount
            + "건 / 전체 "
            + newestFirst.length
            + "건";

        moreButton.style.display =
            visibleCount < newestFirst.length
            ? "block"
            : "none";
    }

    moreButton.addEventListener(
        "click",
        () => {
            visibleCount = Math.min(
                visibleCount + pageSize,
                newestFirst.length
            );
            drawVisibleTransactions();
        }
    );

    drawVisibleTransactions();
}

async function loadCashFlows(
    accessToken,
    accountId
) {
    const data =
        await apiRequest(
            "/api/accounts/"
            + accountId
            + "/cash-flows",
            accessToken
        );

    return data.cash_flows || [];
}


function renderCashFlows(
    container,
    cashFlows,
    account,
    accessToken,
    options = {}
) {
    container.innerHTML = "";

    if (cashFlows.length === 0) {

        const empty =
            document.createElement(
                "div"
            );

        empty.className =
            "empty";

        empty.textContent =
            "아직 등록된 입출금 내역이 없습니다.";

        container.appendChild(
            empty
        );

        return;
    }


    const pageSize = 20;
    const newestFirst = [...cashFlows].sort(
        (a, b) => String(b.flow_date).localeCompare(String(a.flow_date))
            || Number(b.id || 0) - Number(a.id || 0)
    );
    let visibleCount = Math.min(pageSize, newestFirst.length);
    const rowsContainer = document.createElement("div");
    const controls = document.createElement("div");
    controls.className = "transaction-list-controls";
    const count = document.createElement("div");
    count.className = "transaction-list-count";
    const moreButton = document.createElement("button");
    moreButton.type = "button";
    moreButton.className = "small-button secondary-button";
    moreButton.textContent = "20건 더 보기";
    controls.append(count, moreButton);
    container.append(rowsContainer, controls);

    function drawVisibleCashFlows() {
        rowsContainer.innerHTML = "";
        const visibleCashFlows = newestFirst.slice(0, visibleCount);

    for (const cashFlow of visibleCashFlows) {

        const row =
            document.createElement(
                "div"
            );

        row.className =
            "transaction-row";


        const main =
            document.createElement(
                "div"
            );

        main.className =
            "transaction-main";


        const left =
            document.createElement(
                "div"
            );


        const flowType =
            String(
                cashFlow.flow_type
                || ""
            )
            .trim()
            .toUpperCase();


        const typeText =
            flowType === "DEPOSIT"
            ? "입금"
            : "출금";


        left.textContent =
            cashFlow.flow_date
            + " · "
            + typeText;


        left.className =
            flowType === "DEPOSIT"
            ? "sell"
            : "buy";


        const amount =
            document.createElement(
                "div"
            );


        const currency =
            String(
                cashFlow.currency
                || getAccountCurrency(
                    account
                )
            )
            .trim()
            .toUpperCase();


        amount.textContent =
            (
                flowType === "DEPOSIT"
                ? "+"
                : "-"
            )
            + formatMoney(
                cashFlow.amount,
                currency
            );


        main.appendChild(
            left
        );

        main.appendChild(
            amount
        );

        row.appendChild(
            main
        );


        row.appendChild(
            createDetail(
                "통화: "
                + currency
            )
        );


        if (cashFlow.memo) {

            row.appendChild(
                createDetail(
                    "메모: "
                    + cashFlow.memo
                )
            );
        }


        /*
        수정 / 삭제 버튼
        */

        const actions =
            document.createElement(
                "div"
            );

        actions.className =
            "transaction-actions";


        const editButton =
            document.createElement(
                "button"
            );

        editButton.type =
            "button";

        editButton.className =
            "small-button";

        editButton.textContent =
            "수정";


        const deleteButton =
            document.createElement(
                "button"
            );

        deleteButton.type =
            "button";

        deleteButton.className =
            "small-button delete-button";

        deleteButton.textContent =
            "삭제";


        actions.appendChild(
            editButton
        );

        actions.appendChild(
            deleteButton
        );

        row.appendChild(
            actions
        );


        /*
        수정 폼
        */

        editButton.addEventListener(
            "click",
            () => {

                /*
                이미 수정 폼이 열려 있으면
                중복 생성하지 않습니다.
                */

                if (
                    row.querySelector(
                        ".cash-flow-edit-form"
                    )
                ) {
                    return;
                }


                editButton.disabled =
                    true;

                deleteButton.disabled =
                    true;


                const editForm =
                    document.createElement(
                        "form"
                    );

                editForm.className =
                    "transaction-form cash-flow-edit-form";


                /*
                구분
                */

                const typeSelect =
                    document.createElement(
                        "select"
                    );

                typeSelect.innerHTML = `
                    <option value="DEPOSIT">입금</option>
                    <option value="WITHDRAWAL">출금</option>
                `;

                typeSelect.value =
                    flowType;


                /*
                날짜
                */

                const dateInput =
                    document.createElement(
                        "input"
                    );

                dateInput.type =
                    "date";

                dateInput.required =
                    true;

                dateInput.value =
                    cashFlow.flow_date;


                /*
                금액
                */

                const amountInput =
                    document.createElement(
                        "input"
                    );

                amountInput.type =
                    "number";

                amountInput.min =
                    "0.000001";

                amountInput.step =
                    "any";

                amountInput.required =
                    true;

                amountInput.value =
                    String(
                        cashFlow.amount
                        || ""
                    );


                /*
                통화
                */

                const currencySelect =
                    document.createElement(
                        "select"
                    );

                currencySelect.innerHTML = `
                    <option value="KRW">KRW · 원화</option>
                    <option value="USD">USD · 미국 달러</option>
                `;

                currencySelect.value =
                    currency;


                /*
                메모
                */

                const memoInput =
                    document.createElement(
                        "textarea"
                    );

                memoInput.placeholder =
                    "선택사항";

                memoInput.value =
                    cashFlow.memo
                    || "";


                /*
                필드 추가
                */

                function appendField(
                    labelText,
                    element
                ) {
                    const label =
                        document.createElement(
                            "label"
                        );

                    label.textContent =
                        labelText;

                    editForm.appendChild(
                        label
                    );

                    editForm.appendChild(
                        element
                    );
                }


                appendField(
                    "구분",
                    typeSelect
                );

                appendField(
                    "입출금일",
                    dateInput
                );

                appendField(
                    "금액",
                    amountInput
                );

                appendField(
                    "통화",
                    currencySelect
                );

                appendField(
                    "메모",
                    memoInput
                );


                /*
                수정 버튼 영역
                */

                const editActions =
                    document.createElement(
                        "div"
                    );

                editActions.className =
                    "transaction-actions";


                const saveButton =
                    document.createElement(
                        "button"
                    );

                saveButton.type =
                    "submit";

                saveButton.className =
                    "small-button";

                saveButton.textContent =
                    "수정 저장";


                const cancelButton =
                    document.createElement(
                        "button"
                    );

                cancelButton.type =
                    "button";

                cancelButton.className =
                    "small-button";

                cancelButton.textContent =
                    "취소";


                editActions.appendChild(
                    saveButton
                );

                editActions.appendChild(
                    cancelButton
                );

                editForm.appendChild(
                    editActions
                );


                /*
                결과 메시지
                */

                const result =
                    document.createElement(
                        "div"
                    );

                result.className =
                    "transaction-message";

                editForm.appendChild(
                    result
                );


                /*
                취소
                */

                cancelButton.addEventListener(
                    "click",
                    () => {

                        editForm.remove();

                        editButton.disabled =
                            false;

                        deleteButton.disabled =
                            false;
                    }
                );


                /*
                수정 저장
                */

                editForm.addEventListener(
                    "submit",
                    async (event) => {

                        event.preventDefault();


                        const editedAmount =
                            Number(
                                amountInput.value
                            );


                        if (
                            !Number.isFinite(
                                editedAmount
                            )
                            || editedAmount <= 0
                        ) {

                            result.textContent =
                                "0보다 큰 금액을 입력해주세요.";

                            result.className =
                                "transaction-message error";

                            return;
                        }


                        if (!dateInput.value) {

                            result.textContent =
                                "입출금일을 입력해주세요.";

                            result.className =
                                "transaction-message error";

                            return;
                        }


                        const payload = {

                            flow_date:
                                dateInput.value,

                            flow_type:
                                typeSelect.value,

                            amount:
                                editedAmount,

                            currency:
                                currencySelect.value,

                            memo:
                                memoInput
                                .value
                                .trim()
                        };


                        saveButton.disabled =
                            true;

                        cancelButton.disabled =
                            true;

                        saveButton.textContent =
                            "저장 중...";

                        result.textContent =
                            "";


                        try {

                            await apiRequest(
                                "/api/accounts/"
                                + account.id
                                + "/cash-flows/"
                                + cashFlow.id,
                                accessToken,
                                {
                                    method:
                                        "PUT",

                                    headers: {
                                        "Content-Type":
                                            "application/json"
                                    },

                                    body:
                                        JSON.stringify(
                                            payload
                                        )
                                }
                            );


                            if (typeof options.onChanged === "function") {
                                await options.onChanged();
                            } else {
                                await refreshCashFlowData(
                                    account,
                                    accessToken,
                                    container
                                );
                            }


                        } catch (error) {

                            result.textContent =
                                error.message
                                || "입출금 내역 수정에 실패했습니다.";

                            result.className =
                                "transaction-message error";

                            saveButton.disabled =
                                false;

                            cancelButton.disabled =
                                false;

                            saveButton.textContent =
                                "수정 저장";
                        }
                    }
                );


                row.appendChild(
                    editForm
                );
            }
        );


        /*
        삭제
        */

        deleteButton.addEventListener(
            "click",
            async () => {

                const confirmed =
                    window.confirm(
                        cashFlow.flow_date
                        + " "
                        + typeText
                        + " 내역을 삭제할까요?"
                    );

                if (!confirmed) {
                    return;
                }


                editButton.disabled =
                    true;

                deleteButton.disabled =
                    true;


                try {

                    await apiRequest(
                        "/api/accounts/"
                        + account.id
                        + "/cash-flows/"
                        + cashFlow.id,
                        accessToken,
                        {
                            method:
                                "DELETE"
                        }
                    );


                    if (typeof options.onChanged === "function") {
                        await options.onChanged();
                    } else {
                        await refreshCashFlowData(
                            account,
                            accessToken,
                            container
                        );
                    }


                } catch (error) {

                    window.alert(
                        error.message
                        || "입출금 내역 삭제에 실패했습니다."
                    );

                    editButton.disabled =
                        false;

                    deleteButton.disabled =
                        false;
                }
            }
        );


        rowsContainer.appendChild(
            row
        );
    }

        count.textContent = "최근 " + visibleCashFlows.length + "건 / 전체 " + newestFirst.length + "건";
        moreButton.style.display = visibleCount < newestFirst.length ? "block" : "none";
    }

    moreButton.addEventListener("click", () => {
        visibleCount = Math.min(visibleCount + pageSize, newestFirst.length);
        drawVisibleCashFlows();
    });

    drawVisibleCashFlows();
}


async function refreshPortfolioData(
    account,
    targets,
    accessToken,
    transactionsList,
    positionsList
) {
    const [
        transactions,
        positionData
    ] = await Promise.all([
        loadTransactions(
            accessToken,
            account.id
        ),

        loadPositions(
            accessToken,
            account.id
        ),
    ]);


    const positions =
        positionData.positions
        || [];


    const summary =
        positionData.summary
        || null;


    renderTransactions(
        transactionsList,
        transactions,
        targets,
        account,
        accessToken,
        positionsList
    );


    renderPositions(
        positionsList,
        positions,
        account,
        accessToken
    );


    const card =
        positionsList.closest(
            ".account-card"
        );


    if (card) {

        const summaryBox =
            card.querySelector(
                '[data-role="account-summary"]'
            );


        if (summaryBox) {

            renderAccountSummary(
                summaryBox,
                summary,
                account
            );
        }
    }
}


async function showTransactionEditor(
    row,
    transaction,
    targets,
    account,
    accessToken,
    transactionsList,
    positionsList,
    options = {}
) {
    row.innerHTML = "";

    const form =
        document.createElement(
            "form"
        );

    form.className =
        "transaction-form";


    const typeSelect =
        document.createElement(
            "select"
        );

    typeSelect.innerHTML = `
        <option value="BUY">매수</option>
        <option value="SELL">매도</option>
    `;

    typeSelect.value =
        transaction.transaction_type;


    const dateInput =
        document.createElement(
            "input"
        );

    dateInput.type = "date";
    dateInput.required = true;
    dateInput.value =
        transaction.transaction_date;


    const assetSearchInput =
        document.createElement(
            "input"
        );

    assetSearchInput.type =
        "text";

    assetSearchInput.placeholder =
        "종목코드 또는 종목명 검색";

    assetSearchInput.value =
        transaction.ticker;


    const tickerSelect =
        document.createElement(
            "select"
        );

    tickerSelect.required = true;


    const assetInfo =
        document.createElement(
            "div"
        );

    assetInfo.className =
        "transaction-message";


    async function loadAssetOptions(
        keyword = ""
    ) {
        tickerSelect.innerHTML = "";

        const assets =
            await searchRegisteredAssets(
                accessToken,
                keyword
            );

        const assetMap =
            new Map();

        for (const target of targets) {

            assetMap.set(
                target.ticker,
                {
                    ticker:
                        target.ticker,

                    name:
                        target.name,

                    currency:
                        "KRW",
                }
            );
        }

        for (const asset of assets) {
            assetMap.set(
                asset.ticker,
                asset
            );
        }


        if (
            !assetMap.has(
                transaction.ticker
            )
        ) {
            assetMap.set(
                transaction.ticker,
                {
                    ticker:
                        transaction.ticker,

                    name:
                        transaction.name
                        || transaction.ticker,

                    currency:
                        transaction.currency
                        || getAccountCurrency(
                            account
                        ),
                }
            );
        }


        for (
            const asset
            of assetMap.values()
        ) {

            const option =
                document.createElement(
                    "option"
                );

            option.value =
                asset.ticker;

            option.textContent =
                asset.ticker
                + " · "
                + (
                    asset.name
                    || asset.ticker
                )
                + " · "
                + (
                    asset.currency
                    || "-"
                );

            option.dataset.currency =
                asset.currency || "";

            tickerSelect.appendChild(
                option
            );
        }


        tickerSelect.value =
            transaction.ticker;

        updateAssetInfo();
    }


    function updateAssetInfo() {

        const option =
            tickerSelect
            .selectedOptions[0];

        if (!option) {

            assetInfo.textContent =
                "선택 가능한 종목이 없습니다.";

            return;
        }

        assetInfo.textContent =
            "선택 종목: "
            + option.value
            + " · "
            + (
                option.dataset.currency
                || "-"
            );
    }


    tickerSelect.addEventListener(
        "change",
        updateAssetInfo
    );


    let searchTimer = null;

    assetSearchInput.addEventListener(
        "input",
        () => {

            clearTimeout(
                searchTimer
            );

            searchTimer =
                setTimeout(
                    async () => {

                        try {

                            await loadAssetOptions(
                                assetSearchInput
                                .value
                                .trim()
                            );

                        } catch (error) {

                            assetInfo.textContent =
                                error.message
                                || "종목 검색에 실패했습니다.";

                            assetInfo.className =
                                "transaction-message error";
                        }
                    },
                    350
                );
        }
    );


    const quantityInput =
        document.createElement(
            "input"
        );

    quantityInput.type = "number";
    quantityInput.min = "0.000001";
    quantityInput.step = "any";
    quantityInput.required = true;
    quantityInput.value =
        transaction.quantity;


    const priceInput =
        document.createElement(
            "input"
        );

    priceInput.type = "number";
    priceInput.min = "0.000001";
    priceInput.step = "any";
    priceInput.required = true;
    priceInput.value =
        transaction.price;


    const feeInput =
        document.createElement(
            "input"
        );

    feeInput.type = "number";
    feeInput.min = "0";
    feeInput.step = "any";
    feeInput.value =
        transaction.fee || 0;


    const taxInput =
        document.createElement(
            "input"
        );

    taxInput.type = "number";
    taxInput.min = "0";
    taxInput.step = "any";
    taxInput.value =
        transaction.tax || 0;


    const memoInput =
        document.createElement(
            "textarea"
        );

    memoInput.value =
        transaction.memo || "";


    function appendField(
        labelText,
        element
    ) {
        const label =
            document.createElement(
                "label"
            );

        label.textContent =
            labelText;

        form.appendChild(label);
        form.appendChild(element);
    }


    appendField(
        "거래 유형",
        typeSelect
    );

    appendField(
        "거래일",
        dateInput
    );

    appendField(
        "종목 검색",
        assetSearchInput
    );

    appendField(
        "종목 선택",
        tickerSelect
    );

    form.appendChild(
        assetInfo
    );

    appendField(
        "수량",
        quantityInput
    );

    appendField(
        "체결가격",
        priceInput
    );

    appendField(
        "수수료",
        feeInput
    );

    appendField(
        "세금",
        taxInput
    );

    appendField(
        "메모",
        memoInput
    );


    const saveButton =
        document.createElement(
            "button"
        );

    saveButton.type =
        "submit";

    saveButton.textContent =
        "수정 저장";


    const cancelButton =
        document.createElement(
            "button"
        );

    cancelButton.type =
        "button";

    cancelButton.className =
        "cancel-button";

    cancelButton.textContent =
        "취소";


    const result =
        document.createElement(
            "div"
        );

    result.className =
        "transaction-message";


    form.appendChild(
        saveButton
    );

    form.appendChild(
        cancelButton
    );

    form.appendChild(
        result
    );

    row.appendChild(form);


    try {

        await loadAssetOptions("");

    } catch (error) {

        result.textContent =
            error.message
            || "종목 목록을 불러오지 못했습니다.";

        result.className =
            "transaction-message error";
    }


    cancelButton.addEventListener(
        "click",
        async () => {
            if (typeof options.onCancel === "function") {
                await options.onCancel();
            } else {
                await refreshPortfolioData(
                    account,
                    targets,
                    accessToken,
                    transactionsList,
                    positionsList
                );
            }
        }
    );


    form.addEventListener(
        "submit",
        async (event) => {

            event.preventDefault();

            if (!tickerSelect.value) {

                result.textContent =
                    "거래 종목을 선택해주세요.";

                result.className =
                    "transaction-message error";

                return;
            }


            saveButton.disabled =
                true;

            saveButton.textContent =
                "수정 중...";


            const payload = {

                transaction_date:
                    dateInput.value,

                ticker:
                    tickerSelect.value,

                transaction_type:
                    typeSelect.value,

                quantity:
                    Number(
                        quantityInput.value
                    ),

                price:
                    Number(
                        priceInput.value
                    ),

                fee:
                    Number(
                        feeInput.value || 0
                    ),

                tax:
                    Number(
                        taxInput.value || 0
                    ),

                memo:
                    memoInput.value.trim(),
            };


            try {

                await apiRequest(
                    "/api/accounts/"
                    + account.id
                    + "/transactions/"
                    + transaction.id,
                    accessToken,
                    {
                        method:
                            "PUT",

                        headers: {
                            "Content-Type":
                                "application/json",
                        },

                        body:
                            JSON.stringify(
                                payload
                            ),
                    }
                );


                if (typeof options.onSaved === "function") {
                    await options.onSaved();
                } else {
                    await refreshPortfolioData(
                        account,
                        targets,
                        accessToken,
                        transactionsList,
                        positionsList
                    );
                }


            } catch (error) {

                result.textContent =
                    error.message
                    || "거래 수정에 실패했습니다.";

                result.className =
                    "transaction-message error";

                saveButton.disabled =
                    false;

                saveButton.textContent =
                    "수정 저장";
            }
        }
    );
}

function createTransactionForm(
    account,
    targets,
    accessToken,
    transactionsList,
    positionsList,
    options = {}
) {
    const form =
        document.createElement(
            "form"
        );

    form.className =
        "transaction-form";


    const typeSelect =
        document.createElement(
            "select"
        );

    typeSelect.innerHTML = `
        <option value="BUY">매수</option>
        <option value="SELL">매도</option>
    `;


    const dateInput =
        document.createElement(
            "input"
        );

    dateInput.type = "date";
    dateInput.required = true;
    dateInput.value =
        todayString();


    /*
    종목 검색
    */

    const assetSearchInput =
        document.createElement(
            "input"
        );

    assetSearchInput.type =
        "text";

    assetSearchInput.placeholder =
        "종목코드 또는 종목명 검색";

    assetSearchInput.autocomplete =
        "off";

    assetSearchInput.autocapitalize =
        "characters";


    const tickerSelect =
        document.createElement(
            "select"
        );

    tickerSelect.required = true;


    const assetInfo =
        document.createElement(
            "div"
        );

    assetInfo.className =
        "transaction-message";


    /*
    미등록 미국 종목을 Yahoo에서 찾았을 때
    보여줄 영역입니다.
    */

    const yahooResult =
        document.createElement(
            "div"
        );

    yahooResult.style.display =
        "none";


    const button =
        document.createElement(
            "button"
        );

    button.type =
        "submit";

    button.textContent =
        "거래 저장";


    let currentYahooAsset = null;


    function buildAssetMap(
        assets
    ) {
        const assetMap =
            new Map();


        /*
        기존 목표 종목은 항상 선택할 수 있도록
        목록에 포함합니다.
        */

        for (const target of targets) {

            assetMap.set(
                target.ticker,
                {
                    ticker:
                        target.ticker,

                    name:
                        target.name,

                    currency:
                        "KRW",

                    market:
                        "KR",
                }
            );
        }


        /*
        asset_master에 등록된 종목을 추가합니다.
        같은 ticker가 있으면 등록 자산 정보를
        우선 사용합니다.
        */

        for (const asset of assets) {

            assetMap.set(
                asset.ticker,
                asset
            );
        }


        return assetMap;
    }


    function renderAssetOptions(
        assets,
        preferredTicker = ""
    ) {
        tickerSelect.innerHTML = "";

        const assetMap =
            buildAssetMap(
                assets
            );


        for (
            const asset
            of assetMap.values()
        ) {

            const option =
                document.createElement(
                    "option"
                );

            option.value =
                asset.ticker;

            option.textContent =
                asset.ticker
                + " · "
                + (
                    asset.name
                    || asset.ticker
                )
                + " · "
                + (
                    asset.currency
                    || "-"
                );

            option.dataset.currency =
                asset.currency || "";

            option.dataset.market =
                asset.market || "";

            tickerSelect.appendChild(
                option
            );
        }


        const cleanPreferred =
            String(
                preferredTicker || ""
            )
            .trim()
            .toUpperCase();


        if (cleanPreferred) {

            const exactOption =
                Array.from(
                    tickerSelect.options
                ).find(
                    option =>
                        option.value
                        .toUpperCase()
                        === cleanPreferred
                );


            if (exactOption) {

                tickerSelect.value =
                    exactOption.value;
            }
        }


        button.disabled =
            tickerSelect.options.length
            === 0;

        updateAssetInfo();
    }


    function updateAssetInfo() {

        const option =
            tickerSelect
            .selectedOptions[0];


        if (!option) {

            assetInfo.textContent =
                "선택 가능한 종목이 없습니다.";

            return;
        }


        assetInfo.className =
            "transaction-message";


        assetInfo.textContent =
            "선택 종목: "
            + option.value
            + " · "
            + (
                option.dataset.market
                || "-"
            )
            + " · "
            + (
                option.dataset.currency
                || "-"
            );
    }


    function clearYahooResult() {

        currentYahooAsset =
            null;

        yahooResult.innerHTML =
            "";

        yahooResult.style.display =
            "none";
    }


    function showYahooAsset(
        asset
    ) {
        currentYahooAsset =
            asset;

        yahooResult.innerHTML =
            "";

        yahooResult.style.display =
            "block";


        const box =
            document.createElement(
                "div"
            );

        box.className =
            "settings-summary";


        const title =
            document.createElement(
                "div"
            );

        title.style.fontWeight =
            "700";

        title.textContent =
            asset.name
            + " ("
            + asset.ticker
            + ")";


        box.appendChild(
            title
        );


        box.appendChild(
            createDetail(
                "Yahoo Finance에서 확인된 미국 종목"
            )
        );


        box.appendChild(
            createDetail(
                "시장: "
                + asset.market
                + " · 거래소: "
                + asset.exchange
            )
        );


        box.appendChild(
            createDetail(
                "자산 유형: "
                + asset.asset_type
                + " · 통화: "
                + asset.currency
            )
        );


        const registerButton =
            document.createElement(
                "button"
            );

        registerButton.type =
            "button";

        registerButton.textContent =
            "이 종목 등록";


        const registerMessage =
            document.createElement(
                "div"
            );

        registerMessage.className =
            "transaction-message";


        registerButton.addEventListener(
            "click",
            async () => {

                registerButton.disabled =
                    true;

                registerButton.textContent =
                    "등록 중...";

                registerMessage.textContent =
                    "";


                try {

                    const response =
                        await registerUsAsset(
                            accessToken,
                            asset.ticker
                        );


                    if (
                        !response.registered
                        || !response.asset
                    ) {

                        throw new Error(
                            "종목 등록에 실패했습니다."
                        );
                    }


                    const savedAsset =
                        response.asset;


                    /*
                    DB에 실제 저장된 값을 다시 검색합니다.
                    */

                    const assets =
                        await searchRegisteredAssets(
                            accessToken,
                            savedAsset.ticker
                        );


                    renderAssetOptions(
                        assets,
                        savedAsset.ticker
                    );


                    assetSearchInput.value =
                        savedAsset.ticker;


                    registerMessage.textContent =
                        savedAsset.name
                        + " ("
                        + savedAsset.ticker
                        + ") 등록 완료 · 거래 종목으로 선택되었습니다.";


                    registerMessage.className =
                        "transaction-message success";


                    registerButton.textContent =
                        "등록 완료";

                    registerButton.disabled =
                        true;


                } catch (error) {

                    registerMessage.textContent =
                        error.message
                        || "종목 등록에 실패했습니다.";

                    registerMessage.className =
                        "transaction-message error";

                    registerButton.disabled =
                        false;

                    registerButton.textContent =
                        "이 종목 등록";
                }
            }
        );


        box.appendChild(
            registerButton
        );

        box.appendChild(
            registerMessage
        );


        yahooResult.appendChild(
            box
        );
    }


    tickerSelect.addEventListener(
        "change",
        updateAssetInfo
    );


    /*
    검색창 입력 처리

    1. asset_master 검색
    2. 정확한 ticker가 있으면 자동 선택
    3. 등록 종목이 없으면 Yahoo Finance 조회
    */

    let searchTimer = null;

    assetSearchInput.addEventListener(
        "input",
        () => {

            clearTimeout(
                searchTimer
            );


            searchTimer =
                setTimeout(
                    async () => {

                        const keyword =
                            assetSearchInput
                            .value
                            .trim();


                        clearYahooResult();


                        if (!keyword) {

                            try {

                                const assets =
                                    await searchRegisteredAssets(
                                        accessToken,
                                        ""
                                    );


                                renderAssetOptions(
                                    assets
                                );


                            } catch (error) {

                                assetInfo.textContent =
                                    error.message
                                    || "종목 목록을 불러오지 못했습니다.";

                                assetInfo.className =
                                    "transaction-message error";
                            }

                            return;
                        }


                        assetInfo.textContent =
                            "등록된 종목을 검색하는 중...";

                        assetInfo.className =
                            "transaction-message";


                        try {

                            const assets =
                                await searchRegisteredAssets(
                                    accessToken,
                                    keyword
                                );


                            const cleanKeyword =
                                keyword
                                .toUpperCase();


                            const exactAsset =
                                assets.find(
                                    asset =>
                                        String(
                                            asset.ticker
                                        )
                                        .toUpperCase()
                                        === cleanKeyword
                                );


                            /*
                            이미 등록된 ticker라면
                            즉시 자동 선택합니다.
                            */

                            if (exactAsset) {

                                renderAssetOptions(
                                    assets,
                                    exactAsset.ticker
                                );

                                return;
                            }


                            /*
                            종목명 검색 결과가 있으면
                            목록을 보여줍니다.

                            예:
                            "Apple" 검색
                            */

                            if (assets.length > 0) {

                                renderAssetOptions(
                                    assets
                                );

                                return;
                            }


                            /*
                            등록 자산에 없고
                            미국 ticker 형태로 보이는 경우
                            Yahoo Finance에서 확인합니다.
                            */

                            tickerSelect.innerHTML =
                                "";

                            button.disabled =
                                true;


                            assetInfo.textContent =
                                "등록되지 않은 종목입니다. Yahoo Finance에서 확인 중...";


                            try {

                                const response =
                                    await lookupUsAsset(
                                        accessToken,
                                        cleanKeyword
                                    );


                                if (
                                    !response.found
                                    || !response.asset
                                ) {

                                    throw new Error(
                                        "종목 정보를 찾지 못했습니다."
                                    );
                                }


                                showYahooAsset(
                                    response.asset
                                );


                                assetInfo.textContent =
                                    "미등록 미국 종목을 찾았습니다. 아래에서 등록해주세요.";


                            } catch (lookupError) {

                                clearYahooResult();


                                assetInfo.textContent =
                                    lookupError.message
                                    || "등록된 종목을 찾지 못했습니다.";


                                assetInfo.className =
                                    "transaction-message error";
                            }


                        } catch (error) {

                            tickerSelect.innerHTML =
                                "";

                            button.disabled =
                                true;


                            assetInfo.textContent =
                                error.message
                                || "종목 검색에 실패했습니다.";


                            assetInfo.className =
                                "transaction-message error";
                        }

                    },
                    500
                );
        }
    );


    const quantityInput =
        document.createElement(
            "input"
        );

    quantityInput.type = "number";
    quantityInput.min = "0.000001";
    quantityInput.step = "any";
    quantityInput.required = true;


    const priceInput =
        document.createElement(
            "input"
        );

    priceInput.type = "number";
    priceInput.min = "0.000001";
    priceInput.step = "any";
    priceInput.required = true;


    const feeInput =
        document.createElement(
            "input"
        );

    feeInput.type = "number";
    feeInput.min = "0";
    feeInput.step = "any";
    feeInput.value = "0";


    const taxInput =
        document.createElement(
            "input"
        );

    taxInput.type = "number";
    taxInput.min = "0";
    taxInput.step = "any";
    taxInput.value = "0";


    const memoInput =
        document.createElement(
            "textarea"
        );

    memoInput.placeholder =
        "선택사항";


    function appendField(
        labelText,
        element
    ) {

        const label =
            document.createElement(
                "label"
            );

        label.textContent =
            labelText;

        form.appendChild(label);
        form.appendChild(element);
    }


    appendField(
        "거래 유형",
        typeSelect
    );

    appendField(
        "거래일",
        dateInput
    );

    appendField(
        "종목 검색",
        assetSearchInput
    );

    appendField(
        "종목 선택",
        tickerSelect
    );


    form.appendChild(
        assetInfo
    );


    form.appendChild(
        yahooResult
    );


    appendField(
        "수량",
        quantityInput
    );

    appendField(
        "체결가격",
        priceInput
    );

    appendField(
        "수수료",
        feeInput
    );

    appendField(
        "세금",
        taxInput
    );

    appendField(
        "메모",
        memoInput
    );


    const result =
        document.createElement(
            "div"
        );

    result.className =
        "transaction-message";


    form.appendChild(
        button
    );

    form.appendChild(
        result
    );


    /*
    처음 화면을 열었을 때
    등록된 자산을 불러옵니다.
    */

    searchRegisteredAssets(
        accessToken,
        ""
    )
    .then(
        assets => {

            renderAssetOptions(
                assets
            );
        }
    )
    .catch(
        error => {

            button.disabled =
                true;

            assetInfo.textContent =
                error.message
                || "종목 목록을 불러오지 못했습니다.";

            assetInfo.className =
                "transaction-message error";
        }
    );


    form.addEventListener(
        "submit",
        async (event) => {

            event.preventDefault();


            if (!tickerSelect.value) {

                result.textContent =
                    "거래 종목을 먼저 선택해주세요.";

                result.className =
                    "transaction-message error";

                return;
            }


            button.disabled =
                true;

            button.textContent =
                "저장 중...";


            const payload = {

                transaction_date:
                    dateInput.value,

                ticker:
                    tickerSelect.value,

                transaction_type:
                    typeSelect.value,

                quantity:
                    Number(
                        quantityInput.value
                    ),

                price:
                    Number(
                        priceInput.value
                    ),

                fee:
                    Number(
                        feeInput.value || 0
                    ),

                tax:
                    Number(
                        taxInput.value || 0
                    ),

                memo:
                    memoInput.value.trim(),
            };


            try {

                await apiRequest(
                    "/api/accounts/"
                    + account.id
                    + "/transactions",
                    accessToken,
                    {
                        method:
                            "POST",

                        headers: {
                            "Content-Type":
                                "application/json",
                        },

                        body:
                            JSON.stringify(
                                payload
                            ),
                    }
                );


                result.textContent =
                    "거래가 저장되었습니다.";

                result.className =
                    "transaction-message success";


                quantityInput.value = "";
                priceInput.value = "";
                feeInput.value = "0";
                taxInput.value = "0";
                memoInput.value = "";


                await refreshPortfolioData(
                    account,
                    targets,
                    accessToken,
                    transactionsList,
                    positionsList
                );


            } catch (error) {

                result.textContent =
                    error.message
                    || "거래 저장에 실패했습니다.";

                result.className =
                    "transaction-message error";


            } finally {

                button.disabled =
                    tickerSelect.options.length
                    === 0;

                button.textContent =
                    "거래 저장";
            }
        }
    );


    return form;
}

async function refreshCashFlowData(
    account,
    accessToken,
    cashFlowsList
) {
    const [
        cashFlows,
        positionData
    ] = await Promise.all([
        loadCashFlows(
            accessToken,
            account.id
        ),

        loadPositions(
            accessToken,
            account.id
        ),
    ]);


    renderCashFlows(
        cashFlowsList,
        cashFlows,
        account,
        accessToken
    );


    const card =
        cashFlowsList.closest(
            ".account-card"
        );


    if (!card) {
        return;
    }


    const summaryBox =
        card.querySelector(
            '[data-role="account-summary"]'
        );


    if (!summaryBox) {
        return;
    }


    renderAccountSummary(
        summaryBox,
        positionData.summary,
        account
    );
}


function createCashFlowForm(
    account,
    accessToken,
    cashFlowsList,
    options = {}
) {
    const form =
        document.createElement(
            "form"
        );

    form.className =
        "transaction-form";


    /*
    입금 / 출금
    */

    const typeSelect =
        document.createElement(
            "select"
        );

    typeSelect.innerHTML = `
        <option value="DEPOSIT">입금</option>
        <option value="WITHDRAWAL">출금</option>
    `;


    /*
    날짜
    */

    const dateInput =
        document.createElement(
            "input"
        );

    dateInput.type =
        "date";

    dateInput.required =
        true;

    dateInput.value =
        todayString();


    /*
    금액
    */

    const amountInput =
        document.createElement(
            "input"
        );

    amountInput.type =
        "number";

    amountInput.min =
        "0.000001";

    amountInput.step =
        "any";

    amountInput.required =
        true;


    /*
    통화
    */

    const currencySelect =
        document.createElement(
            "select"
        );

    currencySelect.innerHTML = `
        <option value="KRW">KRW · 원화</option>
        <option value="USD">USD · 미국 달러</option>
    `;

    currencySelect.value =
        getAccountCurrency(
            account
        );


    /*
    메모
    */

    const memoInput =
        document.createElement(
            "textarea"
        );

    memoInput.placeholder =
        "예: 계좌 시작자금, 추가 입금";


    /*
    입력 필드 추가 함수
    */

    function appendField(
        labelText,
        element
    ) {
        const label =
            document.createElement(
                "label"
            );

        label.textContent =
            labelText;

        form.appendChild(
            label
        );

        form.appendChild(
            element
        );
    }


    appendField(
        "구분",
        typeSelect
    );

    appendField(
        "입출금일",
        dateInput
    );

    appendField(
        "금액",
        amountInput
    );

    appendField(
        "통화",
        currencySelect
    );

    appendField(
        "메모",
        memoInput
    );


    /*
    저장 버튼
    */

    const button =
        document.createElement(
            "button"
        );

    button.type =
        "submit";

    button.textContent =
        "입출금 저장";


    const result =
        document.createElement(
            "div"
        );

    result.className =
        "transaction-message";


    form.appendChild(
        button
    );

    form.appendChild(
        result
    );


    /*
    저장
    */

    form.addEventListener(
        "submit",
        async (event) => {

            event.preventDefault();


            const amount =
                Number(
                    amountInput.value
                );


            if (
                !Number.isFinite(
                    amount
                )
                || amount <= 0
            ) {

                result.textContent =
                    "0보다 큰 금액을 입력해주세요.";

                result.className =
                    "transaction-message error";

                return;
            }


            button.disabled =
                true;

            button.textContent =
                "저장 중...";

            result.textContent =
                "";


            const payload = {

                flow_date:
                    dateInput.value,

                flow_type:
                    typeSelect.value,

                amount:
                    amount,

                currency:
                    currencySelect.value,

                memo:
                    memoInput
                    .value
                    .trim()
            };


            try {

                await apiRequest(
                    "/api/accounts/"
                    + account.id
                    + "/cash-flows",
                    accessToken,
                    {
                        method:
                            "POST",

                        headers: {
                            "Content-Type":
                                "application/json"
                        },

                        body:
                            JSON.stringify(
                                payload
                            )
                    }
                );


                result.textContent =
                    typeSelect.value
                    === "DEPOSIT"
                    ? "입금 내역이 저장되었습니다."
                    : "출금 내역이 저장되었습니다.";

                result.className =
                    "transaction-message success";


                amountInput.value =
                    "";

                memoInput.value =
                    "";


                /*
                저장 후 입출금 내역과
                계좌 요약을 함께 새로고침
                */

                if (typeof options.onSaved === "function") {
                    await options.onSaved();
                } else {
                    await refreshCashFlowData(
                        account,
                        accessToken,
                        cashFlowsList
                    );
                }


            } catch (error) {

                result.textContent =
                    error.message
                    || "입출금 저장에 실패했습니다.";

                result.className =
                    "transaction-message error";


            } finally {

                button.disabled =
                    false;

                button.textContent =
                    "입출금 저장";
            }
        }
    );


    return form;
}


/*
계좌 설정 편집기
*/

function createAccountEditor(
    account,
    accessToken
) {
    const wrapper =
        document.createElement(
            "div"
        );

    const openButton =
        document.createElement(
            "button"
        );

    openButton.type =
        "button";

    openButton.className =
        "secondary-button";

    openButton.textContent =
        "계좌 설정";

    wrapper.appendChild(
        openButton
    );

    const editor =
        document.createElement(
            "form"
        );

    editor.className =
        "account-editor";

    editor.style.display =
        "none";


    function makeLabel(text) {

        const label =
            document.createElement(
                "label"
            );

        label.textContent =
            text;

        return label;
    }


    function makeInput(
        type,
        value
    ) {
        const input =
            document.createElement(
                "input"
            );

        input.type = type;
        input.value =
            value ?? "";

        return input;
    }


    function makeSelect(
        options,
        value
    ) {
        const select =
            document.createElement(
                "select"
            );

        for (
            const [optionValue, text]
            of options
        ) {
            const option =
                document.createElement(
                    "option"
                );

            option.value =
                optionValue;

            option.textContent =
                text;

            if (
                optionValue === value
            ) {
                option.selected =
                    true;
            }

            select.appendChild(
                option
            );
        }

        return select;
    }


    function addField(
        text,
        element
    ) {
        editor.appendChild(
            makeLabel(text)
        );

        editor.appendChild(
            element
        );
    }


    const accountName =
        makeInput(
            "text",
            account.account_name
        );

    const broker =
        makeInput(
            "text",
            account.broker
        );

    const accountNumber =
        makeInput(
            "text",
            account.account_number
        );


    const accountType =
        makeSelect(
            [
                [
                    "retirement",
                    "퇴직연금"
                ],
                [
                    "pension",
                    "연금계좌"
                ],
                [
                    "isa",
                    "ISA"
                ],
                [
                    "brokerage",
                    "일반 증권계좌"
                ],
            ],
            account.account_type
        );


    const currency =
        makeSelect(
            [
                ["KRW", "KRW · 원화"],
                ["USD", "USD · 달러"],
            ],
            account.currency
        );


    const marketScope =
        makeSelect(
            [
                ["KR", "한국"],
                ["US", "미국"],
                ["GLOBAL", "글로벌"],
            ],
            account.market_scope
        );


    const strategyType =
        makeSelect(
            [
                [
                    "allocation",
                    "자산배분"
                ],
                [
                    "trading",
                    "트레이딩"
                ],
                [
                    "mixed",
                    "혼합"
                ],
            ],
            account.strategy_type
        );


    const initialCapital =
        makeInput(
            "number",
            account.initial_capital
        );

    initialCapital.min = "0";
    initialCapital.step = "any";


    const baseMonthly =
        makeInput(
            "number",
            account.base_monthly
        );

    baseMonthly.min = "0";
    baseMonthly.step = "any";


    const maxAdditional =
        makeInput(
            "number",
            account.max_additional_monthly
        );

    maxAdditional.min = "0";
    maxAdditional.step = "any";


    const contributionType =
        makeSelect(
            [
                [
                    "none",
                    "정기 납입 없음"
                ],
                [
                    "monthly",
                    "매월"
                ],
                [
                    "yearly",
                    "연 1회"
                ],
                [
                    "irregular",
                    "비정기"
                ],
            ],
            account.contribution_type
        );


    const contributionAmount =
        makeInput(
            "number",
            account.contribution_amount
        );

    contributionAmount.min = "0";
    contributionAmount.step = "any";


    const contributionMonth =
        makeInput(
            "number",
            account.contribution_month
            ?? ""
        );

    contributionMonth.min = "1";
    contributionMonth.max = "12";


    const buyCycleType =
        makeSelect(
            [
                [
                    "monthly",
                    "매월"
                ],
                [
                    "irregular",
                    "비정기"
                ],
            ],
            account.buy_cycle_type
        );


    const buyCycleDetail =
        makeInput(
            "text",
            account.buy_cycle_detail
        );


    const memo =
        document.createElement(
            "textarea"
        );

    memo.value =
        account.memo || "";


    addField(
        "계좌 이름",
        accountName
    );

    addField(
        "증권사",
        broker
    );

    addField(
        "계좌번호 / 별칭",
        accountNumber
    );

    addField(
        "계좌 유형",
        accountType
    );

    addField(
        "계좌 기준 통화",
        currency
    );

    addField(
        "투자 시장",
        marketScope
    );

    addField(
        "운용 방식",
        strategyType
    );

    addField(
        "초기 투자재원",
        initialCapital
    );

    addField(
        "월 기본 매수 한도",
        baseMonthly
    );

    addField(
        "월 추가 매수 한도",
        maxAdditional
    );

    addField(
        "외부자금 납입 방식",
        contributionType
    );

    addField(
        "정기 납입금액",
        contributionAmount
    );

    addField(
        "연간 납입월 (연 1회인 경우)",
        contributionMonth
    );

    addField(
        "매수 주기",
        buyCycleType
    );

    addField(
        "매수 기준일 / 설명",
        buyCycleDetail
    );

    addField(
        "메모",
        memo
    );


    const defaultBox =
        document.createElement(
            "div"
        );

    defaultBox.className =
        "checkbox-row";

    const isDefault =
        document.createElement(
            "input"
        );

    isDefault.type =
        "checkbox";

    isDefault.checked =
        Boolean(
            account.is_default
        );

    const defaultLabel =
        document.createElement(
            "label"
        );

    defaultLabel.textContent =
        "기본 계좌";

    defaultBox.appendChild(
        isDefault
    );

    defaultBox.appendChild(
        defaultLabel
    );

    editor.appendChild(
        defaultBox
    );


    const saveButton =
        document.createElement(
            "button"
        );

    saveButton.type =
        "submit";

    saveButton.textContent =
        "계좌 설정 저장";


    const cancelButton =
        document.createElement(
            "button"
        );

    cancelButton.type =
        "button";

    cancelButton.className =
        "cancel-button";

    cancelButton.textContent =
        "취소";


    const result =
        document.createElement(
            "div"
        );

    result.className =
        "transaction-message";


    editor.appendChild(
        saveButton
    );

    editor.appendChild(
        cancelButton
    );

    editor.appendChild(
        result
    );

    wrapper.appendChild(
        editor
    );


    function updateContributionVisibility() {

        const yearly =
            contributionType.value
            === "yearly";

        contributionMonth.disabled =
            !yearly;

        if (!yearly) {
            contributionMonth.value =
                "";
        }
    }


    contributionType.addEventListener(
        "change",
        updateContributionVisibility
    );

    updateContributionVisibility();


    openButton.addEventListener(
        "click",
        () => {

            editor.style.display =
                editor.style.display
                === "none"
                ? "block"
                : "none";
        }
    );


    cancelButton.addEventListener(
        "click",
        () => {

            editor.style.display =
                "none";
        }
    );


    editor.addEventListener(
        "submit",
        async (event) => {

            event.preventDefault();

            saveButton.disabled =
                true;

            saveButton.textContent =
                "저장 중...";

            result.textContent = "";

            const payload = {

                account_name:
                    accountName
                    .value
                    .trim(),

                account_number:
                    accountNumber
                    .value
                    .trim(),

                broker:
                    broker
                    .value
                    .trim(),

                initial_capital:
                    Number(
                        initialCapital.value
                        || 0
                    ),

                base_monthly:
                    Number(
                        baseMonthly.value
                        || 0
                    ),

                max_additional_monthly:
                    Number(
                        maxAdditional.value
                        || 0
                    ),

                buy_cycle_type:
                    buyCycleType.value,

                buy_cycle_detail:
                    buyCycleDetail
                    .value
                    .trim(),

                currency:
                    currency.value,

                account_type:
                    accountType.value,

                market_scope:
                    marketScope.value,

                contribution_type:
                    contributionType.value,

                contribution_amount:
                    Number(
                        contributionAmount.value
                        || 0
                    ),

                contribution_month:
                    (
                        contributionType.value
                        === "yearly"
                        && contributionMonth.value
                    )
                    ? Number(
                        contributionMonth.value
                    )
                    : null,

                strategy_type:
                    strategyType.value,

                is_default:
                    isDefault.checked,

                memo:
                    memo.value.trim(),
            };


            try {

                const response =
                    await saveAccount(
                        accessToken,
                        account.id,
                        payload
                    );

                if (!response.updated) {
                    throw new Error(
                        "계좌 설정 저장에 실패했습니다."
                    );
                }

                result.textContent =
                    "계좌 설정이 저장되었습니다.";

                result.className =
                    "transaction-message success";

                /*
                저장된 DB 값을 다시 읽어 전체 계좌 화면을
                새 값으로 다시 그립니다.
                */
                const accounts =
                    await loadAccounts(
                        accessToken
                    );

                await renderAccounts(
                    accounts,
                    accessToken
                );
                await renderAccountCreator(
                    accounts,
                    accessToken
                );
                await renderAccountManagement(
                    accounts,
                    accessToken
                );
                await loadTransactionTab(
                    accounts,
                    accessToken
                );

            } catch (error) {

                result.textContent =
                    error.message
                    || "계좌 설정을 저장하지 못했습니다.";

                result.className =
                    "transaction-message error";

                saveButton.disabled =
                    false;

                saveButton.textContent =
                    "계좌 설정 저장";
            }
        }
    );

    return wrapper;
}


async function renderAccountManagement(accounts, accessToken) {
    accountManagementList.innerHTML = "";
    if (!accounts.length) {
        accountManagementList.innerHTML = '<div class="empty">등록된 계좌가 없습니다.</div>';
        return;
    }
    for (const account of accounts) {
        const card = document.createElement("div");
        card.className = "account-card";
        const name = document.createElement("div");
        name.className = "account-name";
        name.textContent = account.account_name + (account.is_default ? " · 기본 계좌" : "");
        card.appendChild(name);
        card.appendChild(createDetail((account.broker || "-") + " · " + accountTypeText(account.account_type) + " · " + getAccountCurrency(account)));
        card.appendChild(createAccountEditor(account, accessToken));

        const deleteButton = document.createElement("button");
        deleteButton.type = "button";
        deleteButton.className = "delete-button";
        deleteButton.textContent = "계좌 삭제";
        const message = document.createElement("div");
        message.className = "transaction-message";
        deleteButton.addEventListener("click", async () => {
            const confirmed = window.confirm(
                "'" + account.account_name + "' 계좌를 정말 삭제하시겠습니까?\\n\\n"
                + "이 계좌의 거래내역, 입출금내역, 배당내역, 목표 포트폴리오도 함께 삭제됩니다.\\n\\n"
                + "삭제 후에는 되돌릴 수 없습니다."
            );
            if (!confirmed) return;
            deleteButton.disabled = true;
            deleteButton.textContent = "삭제 중...";
            try {
                const response = await apiRequest("/api/accounts/" + account.id, accessToken, {method: "DELETE"});
                if (!response.deleted) throw new Error("계좌 삭제 결과를 확인할 수 없습니다.");
                const refreshed = await loadAccounts(accessToken);
                await renderAccounts(refreshed, accessToken);
                await renderAccountManagement(refreshed, accessToken);
                await loadTransactionTab(refreshed, accessToken);
            } catch (error) {
                message.textContent = error.message || "계좌 삭제에 실패했습니다.";
                message.className = "transaction-message error";
                deleteButton.disabled = false;
                deleteButton.textContent = "계좌 삭제";
            }
        });
        card.append(deleteButton, message);
        accountManagementList.appendChild(card);
    }
}

async function renderAccountCreator(accounts, accessToken) {
    accountCreator.innerHTML = "";


    /*
    신규 계좌 추가
    */

    const createSection =
        document.createElement(
            "div"
        );

    createSection.className =
        "account-card";


    const createHeader =
        document.createElement(
            "div"
        );

    createHeader.className =
        "account-name";

    createHeader.textContent =
        "+ 새 계좌 추가";

    createSection.appendChild(
        createHeader
    );


    const createDescription =
        createDetail(
            "퇴직연금, ISA, 일반 증권계좌, 미국주식 계좌 등을 추가할 수 있습니다."
        );

    createSection.appendChild(
        createDescription
    );


    const openCreateButton =
        document.createElement(
            "button"
        );

    openCreateButton.type =
        "button";

    openCreateButton.textContent =
        "새 계좌 입력";

    createSection.appendChild(
        openCreateButton
    );


    const createForm =
        document.createElement(
            "form"
        );

    createForm.className =
        "transaction-form";

    createForm.style.display =
        "none";


    function appendCreateField(
        labelText,
        element
    ) {
        const label =
            document.createElement(
                "label"
            );

        label.textContent =
            labelText;

        createForm.appendChild(
            label
        );

        createForm.appendChild(
            element
        );
    }


    /*
    계좌 이름
    */

    const accountNameInput =
        document.createElement(
            "input"
        );

    accountNameInput.type =
        "text";

    accountNameInput.required =
        true;

    accountNameInput.placeholder =
        "예: 미국주식";

    appendCreateField(
        "계좌 이름",
        accountNameInput
    );


    /*
    증권사
    */

    const brokerInput =
        document.createElement(
            "input"
        );

    brokerInput.type =
        "text";

    brokerInput.placeholder =
        "예: 토스증권";

    appendCreateField(
        "증권사",
        brokerInput
    );


    /*
    계좌번호

    선택사항입니다.
    보안상 전체 번호를 입력하지 않아도 됩니다.
    */

    const accountNumberInput =
        document.createElement(
            "input"
        );

    accountNumberInput.type =
        "text";

    accountNumberInput.placeholder =
        "선택사항";

    appendCreateField(
        "계좌번호 또는 식별명",
        accountNumberInput
    );


    /*
    계좌 유형
    */

    const accountTypeSelect =
        document.createElement(
            "select"
        );

    accountTypeSelect.innerHTML = `
        <option value="brokerage">일반 증권계좌</option>
        <option value="isa">ISA</option>
        <option value="retirement">퇴직연금</option>
        <option value="pension">연금계좌</option>
    `;

    appendCreateField(
        "계좌 유형",
        accountTypeSelect
    );


    /*
    기준 통화
    */

    const currencySelect =
        document.createElement(
            "select"
        );

    currencySelect.innerHTML = `
        <option value="KRW">KRW · 원화</option>
        <option value="USD">USD · 미국 달러</option>
    `;

    appendCreateField(
        "계좌 기준 통화",
        currencySelect
    );


    /*
    투자 시장
    */

    const marketScopeSelect =
        document.createElement(
            "select"
        );

    marketScopeSelect.innerHTML = `
        <option value="KR">한국</option>
        <option value="US">미국</option>
        <option value="GLOBAL">글로벌 / 혼합</option>
    `;

    appendCreateField(
        "주요 투자 시장",
        marketScopeSelect
    );


    /*
    운용 방식
    */

    const strategyTypeSelect =
        document.createElement(
            "select"
        );

    strategyTypeSelect.innerHTML = `
        <option value="allocation">자산배분</option>
        <option value="trading">트레이딩</option>
        <option value="mixed">혼합</option>
    `;

    appendCreateField(
        "운용 방식",
        strategyTypeSelect
    );


    /*
    초기 투자재원
    */

    const initialCapitalInput =
        document.createElement(
            "input"
        );

    initialCapitalInput.type =
        "number";

    initialCapitalInput.min =
        "0";

    initialCapitalInput.step =
        "any";

    initialCapitalInput.value =
        "0";

    appendCreateField(
        "초기 투자재원",
        initialCapitalInput
    );


    /*
    월 기본 매수 한도
    */

    const baseMonthlyInput =
        document.createElement(
            "input"
        );

    baseMonthlyInput.type =
        "number";

    baseMonthlyInput.min =
        "0";

    baseMonthlyInput.step =
        "any";

    baseMonthlyInput.value =
        "0";

    appendCreateField(
        "월 기본 매수 한도",
        baseMonthlyInput
    );


    /*
    월 추가 매수 한도
    */

    const additionalMonthlyInput =
        document.createElement(
            "input"
        );

    additionalMonthlyInput.type =
        "number";

    additionalMonthlyInput.min =
        "0";

    additionalMonthlyInput.step =
        "any";

    additionalMonthlyInput.value =
        "0";

    appendCreateField(
        "월 추가 매수 한도",
        additionalMonthlyInput
    );


    /*
    외부자금 납입 방식
    */

    const contributionTypeSelect =
        document.createElement(
            "select"
        );

    contributionTypeSelect.innerHTML = `
        <option value="none">없음</option>
        <option value="monthly">매월</option>
        <option value="yearly">매년</option>
        <option value="irregular">비정기</option>
    `;

    appendCreateField(
        "외부자금 납입 방식",
        contributionTypeSelect
    );


    /*
    외부자금 납입 금액
    */

    const contributionAmountInput =
        document.createElement(
            "input"
        );

    contributionAmountInput.type =
        "number";

    contributionAmountInput.min =
        "0";

    contributionAmountInput.step =
        "any";

    contributionAmountInput.value =
        "0";

    appendCreateField(
        "외부자금 납입 금액",
        contributionAmountInput
    );


    /*
    연간 납입 월
    */

    const contributionMonthSelect =
        document.createElement(
            "select"
        );

    contributionMonthSelect.innerHTML =
        '<option value="">선택 안 함</option>';

    for (
        let month = 1;
        month <= 12;
        month++
    ) {
        const option =
            document.createElement(
                "option"
            );

        option.value =
            String(month);

        option.textContent =
            month + "월";

        contributionMonthSelect
            .appendChild(
                option
            );
    }

    contributionMonthSelect.disabled =
        true;

    appendCreateField(
        "연간 납입 월",
        contributionMonthSelect
    );


    contributionTypeSelect
        .addEventListener(
            "change",
            () => {

                const yearly =
                    contributionTypeSelect
                    .value
                    === "yearly";

                contributionMonthSelect
                    .disabled =
                    !yearly;

                if (!yearly) {
                    contributionMonthSelect
                        .value = "";
                }
            }
        );


    /*
    매수 주기
    */

    const buyCycleTypeSelect =
        document.createElement(
            "select"
        );

    buyCycleTypeSelect.innerHTML = `
        <option value="monthly">매월</option>
        <option value="weekly">매주</option>
        <option value="manual">수동</option>
    `;

    appendCreateField(
        "매수 주기",
        buyCycleTypeSelect
    );


    /*
    매수 주기 상세
    */

    const buyCycleDetailInput =
        document.createElement(
            "input"
        );

    buyCycleDetailInput.type =
        "text";

    buyCycleDetailInput.value =
        "25";

    buyCycleDetailInput.placeholder =
        "매월이면 매수일 입력";

    appendCreateField(
        "매수 주기 상세",
        buyCycleDetailInput
    );


    /*
    기본 계좌
    */

    const defaultWrapper =
        document.createElement(
            "label"
        );

    const defaultCheckbox =
        document.createElement(
            "input"
        );

    defaultCheckbox.type =
        "checkbox";

    defaultWrapper.appendChild(
        defaultCheckbox
    );

    defaultWrapper.appendChild(
        document.createTextNode(
            " 이 계좌를 기본 계좌로 설정"
        )
    );

    createForm.appendChild(
        defaultWrapper
    );


    /*
    메모
    */

    const memoInput =
        document.createElement(
            "textarea"
        );

    memoInput.placeholder =
        "선택사항";

    appendCreateField(
        "메모",
        memoInput
    );


    /*
    생성 / 취소 버튼
    */

    const createButton =
        document.createElement(
            "button"
        );

    createButton.type =
        "submit";

    createButton.textContent =
        "계좌 생성";


    const cancelButton =
        document.createElement(
            "button"
        );

    cancelButton.type =
        "button";

    cancelButton.textContent =
        "취소";


    const createMessage =
        document.createElement(
            "div"
        );

    createMessage.className =
        "transaction-message";


    createForm.appendChild(
        createButton
    );

    createForm.appendChild(
        cancelButton
    );

    createForm.appendChild(
        createMessage
    );


    openCreateButton
        .addEventListener(
            "click",
            () => {

                createForm.style.display =
                    "block";

                openCreateButton.style.display =
                    "none";

                accountNameInput.focus();
            }
        );


    cancelButton
        .addEventListener(
            "click",
            () => {

                createForm.style.display =
                    "none";

                openCreateButton.style.display =
                    "inline-block";

                createMessage.textContent =
                    "";
            }
        );


    /*
    계좌 생성 API 호출
    */

    createForm.addEventListener(
        "submit",
        async (event) => {

            event.preventDefault();


            createButton.disabled =
                true;

            createButton.textContent =
                "생성 중...";

            createMessage.textContent =
                "";


            const contributionMonth =
                contributionMonthSelect.value
                ? Number(
                    contributionMonthSelect.value
                )
                : null;


            const payload = {

                account_name:
                    accountNameInput
                    .value
                    .trim(),

                account_number:
                    accountNumberInput
                    .value
                    .trim(),

                broker:
                    brokerInput
                    .value
                    .trim(),

                initial_capital:
                    Number(
                        initialCapitalInput
                        .value || 0
                    ),

                base_monthly:
                    Number(
                        baseMonthlyInput
                        .value || 0
                    ),

                max_additional_monthly:
                    Number(
                        additionalMonthlyInput
                        .value || 0
                    ),

                buy_cycle_type:
                    buyCycleTypeSelect.value,

                buy_cycle_detail:
                    buyCycleDetailInput
                    .value
                    .trim(),

                currency:
                    currencySelect.value,

                account_type:
                    accountTypeSelect.value,

                market_scope:
                    marketScopeSelect.value,

                contribution_type:
                    contributionTypeSelect.value,

                contribution_amount:
                    Number(
                        contributionAmountInput
                        .value || 0
                    ),

                contribution_month:
                    contributionMonth,

                strategy_type:
                    strategyTypeSelect.value,

                is_default:
                    defaultCheckbox.checked,

                memo:
                    memoInput
                    .value
                    .trim()
            };


            try {

                const response =
                    await apiRequest(
                        "/api/accounts",
                        accessToken,
                        {
                            method:
                                "POST",

                            headers: {
                                "Content-Type":
                                    "application/json"
                            },

                            body:
                                JSON.stringify(
                                    payload
                                )
                        }
                    );


                if (
                    !response.created
                    || !response.account
                ) {
                    throw new Error(
                        "계좌 생성 결과를 확인할 수 없습니다."
                    );
                }


                createMessage.textContent =
                    response.account
                    .account_name
                    + " 계좌가 생성되었습니다.";

                createMessage.className =
                    "transaction-message success";


                /*
                서버에서 계좌 목록을 다시 가져옵니다.
                */

                const refreshed =
                    await apiRequest(
                        "/api/accounts",
                        accessToken
                    );


                const refreshedAccounts =
                    Array.isArray(
                        refreshed
                    )
                    ? refreshed
                    : (
                        refreshed.accounts
                        || []
                    );


                await renderAccounts(refreshedAccounts, accessToken);
                await renderAccountCreator(refreshedAccounts, accessToken);
                await renderAccountManagement(refreshedAccounts, accessToken);
                await loadTransactionTab(refreshedAccounts, accessToken);


            } catch (error) {

                createMessage.textContent =
                    error.message
                    || "계좌 생성에 실패했습니다.";

                createMessage.className =
                    "transaction-message error";


                createButton.disabled =
                    false;

                createButton.textContent =
                    "계좌 생성";
            }
        }
    );


    createSection.appendChild(
        createForm
    );

    accountCreator.appendChild(
        createSection
    );


    /*
    등록된 계좌가 없는 경우에도
    신규 계좌 추가 UI는 유지합니다.
    */

    if (accounts.length === 0) {

        const empty =
            document.createElement(
                "div"
            );

        empty.className =
            "empty";

        empty.textContent =
            "아직 등록된 계좌가 없습니다. 위에서 첫 계좌를 추가해주세요.";

        accountCreator.appendChild(
            empty
        );

        return;
    }


}

async function renderAccounts(
    accounts,
    accessToken
) {
    accountsList.innerHTML = "";

    /*
    기존 계좌 표시
    */

    for (const account of accounts) {

        const card =
            document.createElement(
                "div"
            );

        card.className =
            "account-card";
            
        const name =
            document.createElement(
                "div"
            );

        name.className =
            "account-name";

        name.textContent =
            account.account_name
            + (
                account.is_default
                ? " · 기본 계좌"
                : ""
            );

        card.appendChild(name);

        const summaryTitle =
            document.createElement(
                "div"
            );
        summaryTitle.className =
            "section-title account-summary-title";
        summaryTitle.textContent =
            "계좌 핵심 요약";

        const summaryBox =
            document.createElement(
                "div"
            );
        summaryBox.dataset.role =
            "account-summary";
        summaryBox.className =
            "loading";
        summaryBox.textContent =
            "총자산과 예수금을 불러오는 중...";

        card.appendChild(summaryTitle);
        card.appendChild(summaryBox);


        card.appendChild(
            createDetail(
                "증권사: "
                + (
                    account.broker
                    || "-"
                )
            )
        );


        card.appendChild(
            createDetail(
                "계좌 유형: "
                + accountTypeText(
                    account.account_type
                )
            )
        );


        card.appendChild(
            createDetail(
                "기준 통화: "
                + getAccountCurrency(
                    account
                )
            )
        );


        card.appendChild(
            createDetail(
                "투자 시장: "
                + marketScopeText(
                    account.market_scope
                )
            )
        );


        card.appendChild(
            createDetail(
                "운용 방식: "
                + strategyTypeText(
                    account.strategy_type
                )
            )
        );


        card.appendChild(
            createDetail(
                "초기 투자재원: "
                + formatMoney(
                    account.initial_capital,
                    getAccountCurrency(
                        account
                    )
                )
            )
        );


        card.appendChild(
            createDetail(
                "월 기본 매수 한도: "
                + formatMoney(
                    account.base_monthly,
                    getAccountCurrency(
                        account
                    )
                )
            )
        );


        card.appendChild(
            createDetail(
                "월 추가 매수 한도: "
                + formatMoney(
                    account
                    .max_additional_monthly,
                    getAccountCurrency(
                        account
                    )
                )
            )
        );


        let contributionText =
            "외부자금 납입: "
            + contributionTypeText(
                account.contribution_type
            );


        if (
            Number(
                account.contribution_amount
                || 0
            ) > 0
        ) {

            contributionText +=
                " · "
                + formatMoney(
                    account.contribution_amount,
                    getAccountCurrency(
                        account
                    )
                );
        }


        if (
            account.contribution_type
            === "yearly"
            && account.contribution_month
        ) {

            contributionText +=
                " · "
                + account.contribution_month
                + "월";
        }


        card.appendChild(
            createDetail(
                contributionText
            )
        );


        const cycleText =
            account.buy_cycle_type
            === "monthly"
            ? (
                "매수주기: 매월 "
                + account.buy_cycle_detail
                + "일"
            )
            : (
                "매수주기: "
                + account.buy_cycle_type
                + " / "
                + account.buy_cycle_detail
            );


        card.appendChild(
            createDetail(
                cycleText
            )
        );


        /*
        목표 포트폴리오
        */

        const targetsTitle =
            document.createElement(
                "div"
            );

        targetsTitle.className =
            "section-title";

        targetsTitle.textContent =
            "목표 포트폴리오";

        card.appendChild(
            targetsTitle
        );


        const targetsList =
            document.createElement(
                "div"
            );

        targetsList.className =
            "loading";

        targetsList.textContent =
            "목표 비중을 불러오는 중...";

        card.appendChild(
            targetsList
        );


        accountsList.appendChild(
            card
        );


        try {

            const targets =
                await loadAccountTargets(
                    accessToken,
                    account.id
                );

            renderTargets(
                targetsList,
                targets
            );


            /*
            보유현황
            */

            const positionsTitle =
                document.createElement(
                    "div"
                );

            positionsTitle.className =
                "section-title";

            positionsTitle.textContent =
                "현재 보유현황";

            card.appendChild(
                positionsTitle
            );


            const positionsList =
                document.createElement(
                    "div"
                );

            positionsList.className =
                "loading";

            positionsList.textContent =
                "보유현황을 계산하는 중...";

            card.appendChild(
                positionsList
            );


            try {

                const positionData =
                    await loadPositions(
                        accessToken,
                        account.id
                    );

                const positions =
                    positionData.positions
                    || [];

                const summary =
                    positionData.summary;


                /*
                계좌 요약
                */

                renderAccountSummary(
                    summaryBox,
                    summary,
                    account
                );


                renderPositions(
                    positionsList,
                    positions,
                    account,
                    accessToken
                );

            } catch (error) {

                console.error(
                    "보유현황 오류:",
                    error
                );

                positionsList.className =
                    "error";

                positionsList.textContent =
                    "보유현황 오류: "
                    + (
                        error.name
                        || "Error"
                    )
                    + " / "
                    + (
                        error.message
                        || "알 수 없는 오류"
                    );
            }

            /*
            매수 / 매도 관리는 하단 "거래" 탭에서 통합 관리합니다.
            포트폴리오 화면은 계좌 요약과 보유현황에 집중합니다.
            */

            /*
            입금 / 출금 관리는 하단 "거래" 탭에서 통합 관리합니다.
            */
            
        } catch (error) {

            targetsList.className =
                "error";

            targetsList.textContent =
                error.message
                || "목표 비중을 불러오지 못했습니다.";
        }
    }
}

/*
미국 종목 검색 / 등록
*/

const usAssetSearchForm =
    document.getElementById(
        "us-asset-search-form"
    );

const usAssetTickerInput =
    document.getElementById(
        "us-asset-ticker"
    );

const usAssetSearchButton =
    document.getElementById(
        "us-asset-search-button"
    );

const usAssetSearchResult =
    document.getElementById(
        "us-asset-search-result"
    );


async function registerUsAsset(
    accessToken,
    ticker
) {
    const cleanTicker =
        String(
            ticker || ""
        )
        .trim()
        .toUpperCase();

    if (!cleanTicker) {
        throw new Error(
            "등록할 미국 종목이 없습니다."
        );
    }

    return await apiRequest(
        "/api/assets/us/"
        + encodeURIComponent(
            cleanTicker
        )
        + "/register",
        accessToken,
        {
            method: "POST",
        }
    );
}


function renderUsAssetSearchResult(
    asset,
    accessToken
) {
    usAssetSearchResult.innerHTML = "";

    const resultBox =
        document.createElement(
            "div"
        );

    resultBox.className =
        "settings-summary";


    const title =
        document.createElement(
            "div"
        );

    title.style.fontWeight =
        "700";

    title.style.fontSize =
        "16px";

    title.textContent =
        asset.name
        + " ("
        + asset.ticker
        + ")";

    resultBox.appendChild(
        title
    );


    resultBox.appendChild(
        createDetail(
            "시장: "
            + asset.market
        )
    );

    resultBox.appendChild(
        createDetail(
            "거래소: "
            + asset.exchange
        )
    );

    resultBox.appendChild(
        createDetail(
            "자산 유형: "
            + asset.asset_type
        )
    );

    resultBox.appendChild(
        createDetail(
            "통화: "
            + asset.currency
        )
    );


    const registerButton =
        document.createElement(
            "button"
        );

    registerButton.type =
        "button";

    registerButton.textContent =
        "이 종목 등록";


    const registerMessage =
        document.createElement(
            "div"
        );

    registerMessage.className =
        "transaction-message";


    registerButton.addEventListener(
        "click",
        async () => {

            registerButton.disabled =
                true;

            registerButton.textContent =
                "등록 중...";

            registerMessage.textContent =
                "";

            registerMessage.className =
                "transaction-message";


            try {

                const response =
                    await registerUsAsset(
                        accessToken,
                        asset.ticker
                    );


                if (
                    !response.registered
                    || !response.asset
                ) {
                    throw new Error(
                        "종목 등록에 실패했습니다."
                    );
                }


                const savedAsset =
                    response.asset;


                registerMessage.textContent =
                    savedAsset.name
                    + " ("
                    + savedAsset.ticker
                    + ") 등록이 완료되었습니다.";

                registerMessage.className =
                    "transaction-message success";


                registerButton.textContent =
                    "등록 완료";

                /*
                이미 등록된 자산을 다시 눌러
                불필요하게 반복 요청하지 않도록
                현재 화면에서는 버튼을 비활성화합니다.

                서버의 save_etf_master()도
                같은 ticker가 있으면 INSERT가 아니라
                UPDATE하므로 중복 행은 생성되지 않습니다.
                */
                registerButton.disabled =
                    true;


            } catch (error) {

                registerMessage.textContent =
                    error.message
                    || "종목 등록에 실패했습니다.";

                registerMessage.className =
                    "transaction-message error";

                registerButton.disabled =
                    false;

                registerButton.textContent =
                    "이 종목 등록";
            }
        }
    );


    resultBox.appendChild(
        registerButton
    );

    resultBox.appendChild(
        registerMessage
    );


    usAssetSearchResult.appendChild(
        resultBox
    );

    usAssetSearchResult.className =
        "transaction-message";
}


usAssetSearchForm.addEventListener(
    "submit",
    async (event) => {

        event.preventDefault();

        const accessToken =
            sessionStorage.getItem(
                "access_token"
            );

        if (!accessToken) {

            usAssetSearchResult.textContent =
                "다시 로그인해주세요.";

            usAssetSearchResult.className =
                "transaction-message error";

            return;
        }


        const ticker =
            usAssetTickerInput
            .value
            .trim()
            .toUpperCase();


        if (!ticker) {

            usAssetSearchResult.textContent =
                "미국 종목 티커를 입력해주세요.";

            usAssetSearchResult.className =
                "transaction-message error";

            return;
        }


        usAssetTickerInput.value =
            ticker;

        usAssetSearchButton.disabled =
            true;

        usAssetSearchButton.textContent =
            "검색 중...";

        usAssetSearchResult.textContent =
            "Yahoo Finance에서 종목 정보를 확인하고 있습니다.";

        usAssetSearchResult.className =
            "transaction-message";


        try {

            const response =
                await lookupUsAsset(
                    accessToken,
                    ticker
                );


            if (
                !response.found
                || !response.asset
            ) {
                throw new Error(
                    "종목 정보를 찾지 못했습니다."
                );
            }


            renderUsAssetSearchResult(
                response.asset,
                accessToken
            );


        } catch (error) {

            usAssetSearchResult.textContent =
                error.message
                || "미국 종목 검색에 실패했습니다.";

            usAssetSearchResult.className =
                "transaction-message error";


        } finally {

            usAssetSearchButton.disabled =
                false;

            usAssetSearchButton.textContent =
                "종목 검색";
        }
    }
);

/*
투자성향 저장
*/

const investmentProfileForm =
    document.getElementById(
        "investment-profile-form"
    );


investmentProfileForm.addEventListener(
    "submit",
    async (event) => {

        event.preventDefault();

        const profileMessage =
            document.getElementById(
                "investment-profile-message"
            );

        const accessToken =
            sessionStorage.getItem(
                "access_token"
            );

        if (!accessToken) {

            profileMessage.textContent =
                "다시 로그인해주세요.";

            profileMessage.className =
                "transaction-message error";

            return;
        }


        const horizonValue =
            document.getElementById(
                "investment-horizon"
            ).value;


        const payload = {

            risk_profile:
                document.getElementById(
                    "risk-profile"
                ).value,

            investment_horizon_years:
                horizonValue
                ? Number(
                    horizonValue
                )
                : null,

            /*
            사용자 전체 월 투자금은 더 이상 사용하지
            않습니다. DB 호환성을 위해 0으로 저장합니다.
            */
            monthly_investment: 0,

            ai_advice_style:
                document.getElementById(
                    "ai-advice-style"
                ).value,

            ai_advice_enabled:
                document.getElementById(
                    "ai-advice-enabled"
                ).checked,

            investment_preference_text:
                document.getElementById(
                    "investment-preference-text"
                ).value.trim(),
        };


        profileMessage.textContent =
            "저장 중...";

        profileMessage.className =
            "transaction-message";


        try {

            const result =
                await saveInvestmentProfile(
                    accessToken,
                    payload
                );

            if (!result.saved) {

                throw new Error(
                    "저장에 실패했습니다."
                );
            }

            profileMessage.textContent =
                "투자전략이 저장되었습니다.";

            profileMessage.className =
                "transaction-message success";

        } catch (error) {

            profileMessage.textContent =
                error.message
                || "투자전략을 저장하지 못했습니다.";

            profileMessage.className =
                "transaction-message error";
        }
    }
);


/*
로그인 및 로그인 상태 유지
*/

const adminEmailTestButton = document.getElementById("admin-email-test-button");
const adminEmailTestResult = document.getElementById("admin-email-test-result");
if (adminEmailTestButton && adminEmailTestResult) {
    adminEmailTestButton.addEventListener("click", () =>
        runAdminEmailDiagnostic(adminEmailTestButton, adminEmailTestResult)
    );
}


function saveAuthTokens(
    accessToken,
    refreshToken
) {
    const safeAccessToken =
        accessToken || "";

    const safeRefreshToken =
        refreshToken || "";


    sessionStorage.setItem(
        "access_token",
        safeAccessToken
    );

    sessionStorage.setItem(
        "refresh_token",
        safeRefreshToken
    );


    localStorage.setItem(
        "access_token",
        safeAccessToken
    );

    localStorage.setItem(
        "refresh_token",
        safeRefreshToken
    );
}


function clearAuthTokens() {

    sessionStorage.removeItem(
        "access_token"
    );

    sessionStorage.removeItem(
        "refresh_token"
    );


    localStorage.removeItem(
        "access_token"
    );

    localStorage.removeItem(
        "refresh_token"
    );
}


const logoutButton = document.getElementById("logout-button");
logoutButton.addEventListener("click", () => {
    clearAuthTokens();
    memberManagementTabButton.hidden = true;
    adminSection.hidden = true;
    transactionTabAccounts = [];
    transactionTabAccessToken = "";
    transactionTabRows = [];
    transactionTabVisibleCount = 20;
    transactionAccountFilter.innerHTML = '<option value="">전체 계좌</option>';
    transactionTypeFilter.value = "";
    transactionSearchFilter.value = "";
    allTransactionsList.innerHTML = "";
    allCashFlowsList.innerHTML = "";
    accountsList.innerHTML = "";
    accountCreator.innerHTML = "";
    accountManagementList.innerHTML = "";
    adminMembers.innerHTML = "불러오는 중...";
    activeSettingsPanel = "accounts";
    setAppTab("home", {scroll: false});
    appArea.style.display = "none";
    loginCard.style.display = "block";
    loginStatus.textContent = "로그인 완료";
    loginForm.reset();
    message.textContent = "";
    window.scrollTo({top: 0, behavior: "smooth"});
});


async function showAuthenticatedApp(
    accessToken
) {
    const user =
        await verifyUser(
            accessToken
        );


    const bootstrapResponse =
        await fetch(
            "/api/bootstrap",
            {
                method: "POST",
                headers: {
                    "Authorization":
                        "Bearer "
                        + accessToken,
                },
            }
        );

    if (!bootstrapResponse.ok) {
        let detail =
            "사용자 초기 설정을 준비하지 못했습니다.";

        try {
            const bootstrapData =
                await bootstrapResponse.json();

            detail =
                bootstrapData.detail
                || detail;
        } catch (error) {}

        throw new Error(detail);
    }


    const [
        accounts,
        investmentProfile
    ] = await Promise.all([

        loadAccounts(
            accessToken
        ),

        loadInvestmentProfile(
            accessToken
        ),
    ]);


    if (investmentProfile) {

        document.getElementById(
            "risk-profile"
        ).value =
            investmentProfile
            .risk_profile
            || "balanced";


        document.getElementById(
            "investment-horizon"
        ).value =
            investmentProfile
            .investment_horizon_years
            ?? "";


        document.getElementById(
            "ai-advice-style"
        ).value =
            investmentProfile
            .ai_advice_style
            || "balanced";


        document.getElementById(
            "ai-advice-enabled"
        ).checked =
            investmentProfile
            .ai_advice_enabled
            !== false;


        document.getElementById(
            "investment-preference-text"
        ).value =
            investmentProfile
            .investment_preference_text
            || "";
    }


    await renderAccounts(
        accounts,
        accessToken
    );
    await renderAccountCreator(accounts, accessToken);
    await renderAccountManagement(accounts, accessToken);

    try {
        await loadTransactionTab(accounts, accessToken);
    } catch (error) {
        allTransactionsList.className = "error";
        allTransactionsList.textContent = error.message || "전체 거래 내역을 불러오지 못했습니다.";
    }

    try {
        await loadAdminPanel(accessToken);
    } catch (error) {
        console.error("관리자 화면 로딩 오류:", error);
        memberManagementTabButton.hidden = true;
        adminSection.hidden = true;
    }

    try {
        await loadMorningReportSettings(accessToken);
    } catch (error) {
        morningReportSettingsMessage.textContent = error.message || "모닝 리포트 설정을 불러오지 못했습니다.";
    }

    try {
        await loadKakaoStatus(accessToken);
    } catch (error) {
        kakaoStatus.textContent = error.message || "카카오 연결 상태를 확인하지 못했습니다.";
        kakaoStatus.className = "status-box error";
    }


    loginStatus.textContent =
        "로그인 완료 · "
        + (
            user.email
            || "사용자"
        )
        + " · 등록된 계좌 "
        + accounts.length
        + "개";


    loginCard.style.display =
        "none";


    appArea.style.display =
        "flex";

    if (!reportRequested) {
        setAppTab("home", {scroll: false});
    }

    if (reportRequested) {
        document.getElementById("kakao-settings-section").style.display = "none";
        document.getElementById("investment-settings-section").style.display = "none";
        document.getElementById("asset-search-section").style.display = "none";
        document.getElementById("portfolio-section").style.display = "none";
        await showPrivateReport(accessToken);
    }


    /*
    앱 영역을 먼저 표시한 뒤
    직접 연결된 종목으로 이동합니다.
    */
    openLinkedAssetChart();
}


async function refreshLoginSession(
    refreshToken
) {
    if (!refreshToken) {
        return null;
    }


    const response =
        await fetch(
            SUPABASE_URL
            + "/auth/v1/token"
            + "?grant_type=refresh_token",
            {
                method:
                    "POST",

                headers: {
                    "Content-Type":
                        "application/json",

                    "apikey":
                        SUPABASE_KEY,
                },

                body:
                    JSON.stringify({
                        refresh_token:
                            refreshToken,
                    }),
            }
        );


    const data =
        await response.json();


    if (
        !response.ok
        || !data.access_token
    ) {
        return null;
    }


    saveAuthTokens(
        data.access_token,
        data.refresh_token
        || refreshToken
    );


    return data.access_token;
}


async function restoreLoginSession() {

    const savedAccessToken =
        localStorage.getItem(
            "access_token"
        );


    const savedRefreshToken =
        localStorage.getItem(
            "refresh_token"
        );


    console.log(
        "자동 로그인 확인:",
        {
            hasAccessToken:
                Boolean(
                    savedAccessToken
                ),

            hasRefreshToken:
                Boolean(
                    savedRefreshToken
                ),
        }
    );


    if (
        !savedAccessToken
        && !savedRefreshToken
    ) {

        console.log(
            "저장된 로그인 정보가 없습니다."
        );

        return;
    }


    message.textContent =
        "로그인 상태를 확인하고 있습니다.";

    message.className = "";


    let accessToken =
        savedAccessToken;


    /*
    1단계:
    저장된 access token 자체가
    유효한지만 먼저 확인합니다.

    계좌 로딩이나 화면 렌더링 오류를
    인증 실패로 판단하지 않습니다.
    */
    if (accessToken) {

        try {

            await verifyUser(
                accessToken
            );


            console.log(
                "저장된 access token이 유효합니다."
            );


        } catch (error) {

            console.log(
                "access token 확인 실패. "
                + "refresh token을 사용합니다."
            );


            accessToken =
                null;
        }
    }


    /*
    2단계:
    access token이 없거나 만료된 경우에만
    refresh token으로 새 access token을 받습니다.
    */
    if (!accessToken) {

        if (!savedRefreshToken) {

            clearAuthTokens();


            message.textContent =
                "로그인 시간이 만료되었습니다. 다시 로그인해주세요.";

            message.className =
                "error";


            return;
        }


        try {

            accessToken =
                await refreshLoginSession(
                    savedRefreshToken
                );


        } catch (error) {

            console.error(
                "로그인 갱신 오류:",
                error
            );


            accessToken =
                null;
        }


        if (!accessToken) {

            clearAuthTokens();


            message.textContent =
                "로그인 시간이 만료되었습니다. 다시 로그인해주세요.";

            message.className =
                "error";


            return;
        }


        console.log(
            "refresh token으로 로그인 상태를 갱신했습니다."
        );
    }


    /*
    기존 코드의 다른 기능들이
    sessionStorage의 access_token을 사용하므로
    현재 세션에도 다시 복사합니다.
    */
    const currentRefreshToken =
        localStorage.getItem(
            "refresh_token"
        )
        || savedRefreshToken
        || "";


    saveAuthTokens(
        accessToken,
        currentRefreshToken
    );


    /*
    3단계:
    인증 성공 이후에 앱 데이터를 불러옵니다.

    여기서 오류가 발생해도 인증 토큰을
    삭제하지 않습니다.
    */
    try {

        await showAuthenticatedApp(
            accessToken
        );


        message.textContent = "";


        console.log(
            "자동 로그인 완료"
        );


    } catch (error) {

        console.error(
            "자동 로그인 후 앱 로딩 오류:",
            error
        );


        message.textContent =
            "로그인은 유지되어 있지만 "
            + "포트폴리오를 불러오지 못했습니다. "
            + "페이지를 다시 열어주세요.";

        message.className =
            "error";
    }
}

async function refreshSignupAvailability() {
    try {
        const response = await fetch("/api/signup-status");
        const data = await response.json();
        const enabled = response.ok && Boolean(data.signup_enabled);
        showSignupButton.style.display = enabled ? "block" : "none";
        if (!enabled) signupForm.style.display = "none";
    } catch (_) {
        showSignupButton.style.display = "none";
        signupForm.style.display = "none";
    }
}

showSignupButton.addEventListener("click", () => {
    const opening = signupForm.style.display === "none";
    signupForm.style.display = opening ? "block" : "none";
    showSignupButton.textContent = opening ? "회원가입 닫기" : "회원가입";
    message.textContent = "";
    message.className = "";
});

signupForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    message.textContent = "";
    message.className = "";
    signupButton.disabled = true;
    signupButton.textContent = "가입 중...";
    const email = document.getElementById("signup-email").value.trim();
    const password = document.getElementById("signup-password").value;
    try {
        const response = await fetch("/api/auth/signup", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({email, password}),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "회원가입에 실패했습니다.");
        if (data.access_token) {
            saveAuthTokens(data.access_token, data.refresh_token || "");
            await showAuthenticatedApp(data.access_token);
            message.textContent = "";
            return;
        }
        document.getElementById("email").value = email;
        signupForm.style.display = "none";
        showSignupButton.textContent = "회원가입";
        message.textContent = "회원가입이 완료되었습니다.";
        message.className = "success";
    } catch (error) {
        message.textContent = error.message || "회원가입에 실패했습니다.";
        message.className = "error";
        await refreshSignupAvailability();
    } finally {
        signupButton.disabled = false;
        signupButton.textContent = "회원가입";
    }
});

refreshSignupAvailability();

loginForm.addEventListener(
    "submit",
    async (event) => {

        event.preventDefault();


        message.textContent = "";
        message.className = "";


        loginButton.disabled =
            true;


        loginButton.textContent =
            "로그인 중...";


        const email =
            document.getElementById(
                "email"
            ).value.trim();


        const password =
            document.getElementById(
                "password"
            ).value;


        try {

            const response =
                await fetch(
                    SUPABASE_URL
                    + "/auth/v1/token"
                    + "?grant_type=password",
                    {
                        method:
                            "POST",

                        headers: {
                            "Content-Type":
                                "application/json",

                            "apikey":
                                SUPABASE_KEY,
                        },

                        body:
                            JSON.stringify({
                                email:
                                    email,

                                password:
                                    password,
                            }),
                    }
                );


            const data =
                await response.json();


            if (
                !response.ok
                || !data.access_token
            ) {

                throw new Error(
                    data.error_description
                    || data.msg
                    || "로그인에 실패했습니다."
                );
            }


            saveAuthTokens(
                data.access_token,
                data.refresh_token
                || ""
            );


            loginButton.textContent =
                "계좌 확인 중...";


            await showAuthenticatedApp(
                data.access_token
            );


        } catch (error) {

            clearAuthTokens();


            message.textContent =
                error.message
                || "로그인에 실패했습니다.";


            message.className =
                "error";


        } finally {

            loginButton.disabled =
                false;


            loginButton.textContent =
                "로그인";
        }
    }
);


/*
페이지를 새로 열었을 때
저장된 Supabase 세션으로 자동 로그인합니다.
*/
async function loadPublicSignupStatus() {
    try {
        const response = await fetch("/api/signup-status");
        const data = await response.json();
        const enabled = response.ok && Boolean(data.signup_enabled);
        showSignupButton.style.display = enabled ? "block" : "none";
        if (!enabled) signupForm.style.display = "none";
    } catch (error) {
        showSignupButton.style.display = "none";
    }
}

loadPublicSignupStatus();

restoreLoginSession().finally(() => {
    bootScreen.style.display = "none";

    if (appArea.style.display === "none" || !appArea.style.display) {
        loginCard.style.display = "block";
    }
});

</script>

</body>

</html>
    """

    html = html.replace(
        "__SUPABASE_URL_JSON__",
        json.dumps(supabase_url),
    )

    html = html.replace(
        "__SUPABASE_KEY_JSON__",
        json.dumps(supabase_key),
    )

    return HTMLResponse(
        content=html
    )
