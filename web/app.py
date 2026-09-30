"""
web/app.py

RetirementPortfolio 모바일 웹 애플리케이션.
"""

from __future__ import annotations

import json
import os

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from supabase import create_client
from services.portfolio_service import PortfolioService

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


# =========================================================
# Request Models
# =========================================================

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

    transaction_date: str = Field(
        min_length=8,
        max_length=10,
    )

    ticker: str = Field(
        min_length=1,
        max_length=30,
    )

    transaction_type: str = Field(
        min_length=3,
        max_length=4,
    )

    quantity: float = Field(gt=0)
    price: float = Field(ge=0)
    fee: float = Field(default=0, ge=0)
    tax: float = Field(default=0, ge=0)

    memo: str = Field(
        default="",
        max_length=1000,
    )

class CashFlowRequest(BaseModel):
    flow_date: str
    flow_type: str
    amount: float = Field(gt=0)
    currency: str
    memo: str = ""
    
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
        # initial_capital은 실제 현금으로 자동 포함하지 않습니다.
        #
        # 현금잔고 =
        # 입금
        # - 출금
        # - 매수
        # + 매도
        # + 배당 실수령액
        # -----------------------------------------------------

        cash_balance = (
            portfolio_service
            .get_cash_balance(
                account_id=account_id,
                include_initial_capital=False,
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
    content="width=device-width, initial-scale=1.0"
>

<title>RetirementPortfolio</title>

<style>

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    padding: 20px 14px 50px;
    background: #f5f7fa;
    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;
    color: #202124;
}

.container {
    width: 100%;
    max-width: 560px;
    margin: 20px auto;
}

.card {
    background: white;
    border-radius: 18px;
    padding: 24px 20px;
    margin-bottom: 16px;
    box-shadow:
        0 2px 14px rgba(0,0,0,0.08);
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
}

button:disabled {
    opacity: 0.55;
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

.buy {
    color: #b3261e;
}

.sell {
    color: #137333;
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
    touch-action: manipulation;
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

.asset-chart-loading {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 230px;
    color: #777;
    font-size: 13px;
}

@media (max-width: 380px) {
    .form-row {
        grid-template-columns: 1fr;
        gap: 0;
    }
}

</style>

</head>


<body>

<main class="container">

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

<div id="message"></div>

<div class="security">
비밀번호 인증은 Supabase Auth가 처리하며
포트폴리오 데이터베이스에는 비밀번호를
저장하지 않습니다.
</div>

</section>


<div id="app-area">

<section class="card">

<h1>RetirementPortfolio</h1>

<div
    id="login-status"
    class="status-box"
>
로그인 완료
</div>

</section>


<section class="card">

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


<section class="card">

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


<section class="card">

<h2>내 계좌</h2>

<div id="accounts-list"></div>

</section>

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

const loginForm =
    document.getElementById(
        "login-form"
    );

const loginButton =
    document.getElementById(
        "login-button"
    );

const message =
    document.getElementById(
        "message"
    );

const appArea =
    document.getElementById(
        "app-area"
    );

const loginStatus =
    document.getElementById(
        "login-status"
    );

const accountsList =
    document.getElementById(
        "accounts-list"
    );


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


    const prices =
        Array.isArray(
            chartData.prices
        )
            ? chartData.prices
            : [];


    const transactions =
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
        prices.filter(
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
        validPrices.map(
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
                ? minimumPrice * 0.02
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


    function getX(index) {

        if (
            validPrices.length === 1
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
                    validPrices.length
                    - 1
                )
            )
            * plotWidth
        );
    }


    function getY(price) {

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
        return document.createElementNS(
            "http://www.w3.org/2000/svg",
            tagName
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
        validPrices.length
        + "개 가격 데이터";


    summary.appendChild(
        latestPriceElement
    );

    summary.appendChild(
        period
    );

    container.appendChild(
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
                ? gridPrice.toFixed(2)
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
        validPrices.map(
            (item, index) => {

                return (
                    getX(index)
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
        points.join(" ")
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
                validPrices.length
                - 1
            )
            / 2
        ),
        validPrices.length - 1,
    ];


    const uniqueDateIndexes =
        [
            ...new Set(
                dateIndexes
            ),
        ];


    for (
        const index
        of uniqueDateIndexes
    ) {

        const item =
            validPrices[index];


        if (!item) {
            continue;
        }


        const dateLabel =
            createSvgElement(
                "text"
            );


        let anchor =
            "middle";


        if (index === 0) {
            anchor =
                "start";
        }


        if (
            index
            === validPrices.length - 1
        ) {
            anchor =
                "end";
        }


        dateLabel.setAttribute(
            "x",
            getX(index)
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
            new Date(
                item.date
                + "T00:00:00"
            );


        if (
            Number.isNaN(
                date.getTime()
            )
        ) {
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

        const targetTime =
            new Date(
                transactionDate
                + "T00:00:00"
            ).getTime();


        if (
            !Number.isFinite(
                targetTime
            )
        ) {
            return 0;
        }


        let nearestIndex =
            0;

        let nearestDifference =
            Infinity;


        for (
            let index = 0;
            index < validPrices.length;
            index += 1
        ) {

            const priceTime =
                new Date(
                    validPrices[index].date
                    + "T00:00:00"
                ).getTime();


            if (
                !Number.isFinite(
                    priceTime
                )
            ) {
                continue;
            }


            const difference =
                Math.abs(
                    priceTime
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


        const x =
            getX(
                nearestIndex
            );

        const y =
            getY(
                transactionPrice
            );


        const marker =
            createSvgElement(
                "circle"
            );

        marker.setAttribute(
            "cx",
            x
        );

        marker.setAttribute(
            "cy",
            y
        );

        marker.setAttribute(
            "r",
            "6"
        );


        const transactionType =
            String(
                transaction.type
                || ""
            ).toUpperCase();


        if (
            transactionType
            === "SELL"
        ) {
            marker.setAttribute(
                "fill",
                "#137333"
            );
        } else {
            marker.setAttribute(
                "fill",
                "#b3261e"
            );
        }


        marker.setAttribute(
            "stroke",
            "#ffffff"
        );

        marker.setAttribute(
            "stroke-width",
            "2"
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

    container.appendChild(
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
        + "매수";


    const sellLegend =
        document.createElement(
            "div"
        );

    sellLegend.className =
        "asset-chart-legend-item";

    sellLegend.innerHTML =
        '<span class="asset-chart-marker sell-marker"></span>'
        + "매도";


    legend.appendChild(
        buyLegend
    );

    legend.appendChild(
        sellLegend
    );

    container.appendChild(
        legend
    );

    container.appendChild(
        tooltip
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
        "transaction-row";


    const summaryCurrency =
        String(
            summary.currency
            || getAccountCurrency(
                account
            )
        )
        .trim()
        .toUpperCase();


    container.appendChild(
        createDetail(
            "총 매수원가: "
            + formatMoney(
                summary.total_invested,
                summaryCurrency
            )
        )
    );


    container.appendChild(
        createDetail(
            "주식 평가액: "
            + formatMoney(
                summary.total_current_value,
                summaryCurrency
            )
        )
    );


    container.appendChild(
        createDetail(
            "현금잔고: "
            + formatMoney(
                summary.cash_balance,
                summaryCurrency
            )
        )
    );


    container.appendChild(
        createDetail(
            "총자산: "
            + formatMoney(
                summary.total_assets,
                summaryCurrency
            )
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


    const totalPnlDetail =
        createDetail(
            "총손익: "
            + (
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
                Number(
                    summary.total_roi
                    || 0
                ) > 0
                ? "+"
                : ""
            )
            + formatPercent(
                summary.total_roi
            )
            + ")"
        );


    if (totalPnl > 0) {

        totalPnlDetail.classList.add(
            "sell"
        );
    }


    if (totalPnl < 0) {

        totalPnlDetail.classList.add(
            "buy"
        );
    }


    container.appendChild(
        totalPnlDetail
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

        name.textContent =
            position.name
            || position.ticker;


        const value =
            document.createElement(
                "div"
            );

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


                    const status =
                        document.createElement(
                            "div"
                        );

                    status.className =
                        "status-box";


                    const priceCount =
                        Number(
                            chartData.price_count
                            || 0
                        );


                    const transactionCount =
                        Number(
                            chartData.transaction_count
                            || 0
                        );


                    status.innerHTML =
                        "가격 데이터 "
                        + priceCount
                        + "개"
                        + "<br>"
                        + "매매 기록 "
                        + transactionCount
                        + "개";


                    chartPanel.appendChild(
                        status
                    );


                    if (
                        priceCount > 0
                        && transactionCount > 0
                    ) {

                        const success =
                            document.createElement(
                                "div"
                            );

                        success.className =
                            "transaction-detail success";

                        success.style.marginTop =
                            "10px";

                        success.textContent =
                            "차트 데이터를 정상적으로 불러왔습니다.";

                        chartPanel.appendChild(
                            success
                        );

                    } else {

                        const warning =
                            document.createElement(
                                "div"
                            );

                        warning.className =
                            "transaction-detail";

                        warning.style.marginTop =
                            "10px";

                        if (
                            priceCount === 0
                        ) {
                            warning.textContent =
                                "저장된 가격 데이터가 없습니다.";
                        } else {
                            warning.textContent =
                                "이 기간의 매매 기록이 없습니다.";
                        }

                        chartPanel.appendChild(
                            warning
                        );
                    }


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

    for (
        const transaction
        of newestFirst
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


        container.appendChild(row);
    }
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
    accessToken
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


    for (const cashFlow of cashFlows) {

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


                            await refreshCashFlowData(
                                account,
                                accessToken,
                                container
                            );


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


                    await refreshCashFlowData(
                        account,
                        accessToken,
                        container
                    );


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


        container.appendChild(
            row
        );
    }
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
    positionsList
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
    priceInput.min = "0";
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

            await refreshPortfolioData(
                account,
                targets,
                accessToken,
                transactionsList,
                positionsList
            );
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
    positionsList
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
    priceInput.min = "0";
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
    cashFlowsList
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

                await refreshCashFlowData(
                    account,
                    accessToken,
                    cashFlowsList
                );


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


async function renderAccounts(
    accounts,
    accessToken
) {
    accountsList.innerHTML = "";


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


                await renderAccounts(
                    refreshedAccounts,
                    accessToken
                );


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

    accountsList.appendChild(
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

        accountsList.appendChild(
            empty
        );

        return;
    }


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
        계좌 설정
        */

        card.appendChild(
            createAccountEditor(
                account,
                accessToken
            )
        );

        /*
        계좌 삭제
        */
        
        const deleteAccountButton =
            document.createElement(
                "button"
            );
        
        deleteAccountButton.type =
            "button";
        
        deleteAccountButton.textContent =
            "계좌 삭제";
        
        
        const deleteAccountMessage =
            document.createElement(
                "div"
            );
        
        deleteAccountMessage.className =
            "transaction-message";
        
        
        deleteAccountButton.addEventListener(
            "click",
            async () => {
        
                const confirmed =
                    window.confirm(
                        "'"
                        + account.account_name
                        + "' 계좌를 정말 삭제하시겠습니까?\\n\\n"
                        + "이 계좌의 거래내역, 배당내역, "
                        + "목표 포트폴리오도 함께 삭제됩니다.\\n\\n"
                        + "삭제 후에는 되돌릴 수 없습니다."
                    );        
        
                if (!confirmed) {
                    return;
                }
        
        
                deleteAccountButton.disabled =
                    true;
        
                deleteAccountButton.textContent =
                    "삭제 중...";
        
                deleteAccountMessage.textContent =
                    "";
        
        
                try {
        
                    const response =
                        await apiRequest(
                            "/api/accounts/"
                            + account.id,
                            accessToken,
                            {
                                method:
                                    "DELETE"
                            }
                        );
        
        
                    if (!response.deleted) {
                        throw new Error(
                            "계좌 삭제 결과를 확인할 수 없습니다."
                        );
                    }
        
        
                    /*
                    삭제 후 서버에서 최신 계좌 목록을
                    다시 가져옵니다.
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
        
        
                    await renderAccounts(
                        refreshedAccounts,
                        accessToken
                    );
        
        
                } catch (error) {
        
                    deleteAccountMessage.textContent =
                        error.message
                        || "계좌 삭제에 실패했습니다.";
        
                    deleteAccountMessage.className =
                        "transaction-message error";
        
                    deleteAccountButton.disabled =
                        false;
        
                    deleteAccountButton.textContent =
                        "계좌 삭제";
                }
            }
        );
        
        
        card.appendChild(
            deleteAccountButton
        );
        
        card.appendChild(
            deleteAccountMessage
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

                const summaryTitle =
                    document.createElement(
                        "div"
                    );

                summaryTitle.className =
                    "section-title";

                summaryTitle.textContent =
                    "계좌 요약";


                const summaryBox =
                    document.createElement(
                        "div"
                    );

                summaryBox.dataset.role =
                    "account-summary";                


                renderAccountSummary(
                    summaryBox,
                    summary,
                    account
                );


                card.insertBefore(
                    summaryTitle,
                    positionsTitle
                );

                card.insertBefore(
                    summaryBox,
                    positionsTitle
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
            거래 입력
            */

            const formTitle =
                document.createElement(
                    "div"
                );

            formTitle.className =
                "section-title";

            formTitle.textContent =
                "매수 / 매도 입력";

            card.appendChild(
                formTitle
            );


            const transactionsList =
                document.createElement(
                    "div"
                );


            const transactionForm =
                createTransactionForm(
                    account,
                    targets,
                    accessToken,
                    transactionsList,
                    positionsList
                );

            card.appendChild(
                transactionForm
            );


            /*
            거래 내역
            */

            const transactionsTitle =
                document.createElement(
                    "div"
                );

            transactionsTitle.className =
                "section-title";

            transactionsTitle.textContent =
                "거래 내역";

            card.appendChild(
                transactionsTitle
            );


            card.appendChild(
                transactionsList
            );


            try {

                const transactions =
                    await loadTransactions(
                        accessToken,
                        account.id
                    );

                renderTransactions(
                    transactionsList,
                    transactions,
                    targets,
                    account,
                    accessToken,
                    positionsList
                );

            } catch (error) {

                transactionsList.className =
                    "error";

                transactionsList.textContent =
                    error.message
                    || "거래 내역을 불러오지 못했습니다.";
            }

            /*
            현금 입출금 입력
            */

            const cashFlowFormTitle =
                document.createElement(
                    "div"
                );

            cashFlowFormTitle.className =
                "section-title";

            cashFlowFormTitle.textContent =
                "입금 / 출금 입력";

            card.appendChild(
                cashFlowFormTitle
            );


            /*
            현금 입출금 내역
            */

            const cashFlowsTitle =
                document.createElement(
                    "div"
                );

            cashFlowsTitle.className =
                "section-title";

            cashFlowsTitle.textContent =
                "입금 / 출금 내역";


            const cashFlowsList =
                document.createElement(
                    "div"
                );

            cashFlowsList.className =
                "loading";

            cashFlowsList.textContent =
                "입출금 내역을 불러오는 중...";


            /*
            입력 폼

            cashFlowsList를 전달하여
            저장 직후 내역을 바로 갱신합니다.
            */

            const cashFlowForm =
                createCashFlowForm(
                    account,
                    accessToken,
                    cashFlowsList
                );


            card.appendChild(
                cashFlowForm
            );

            card.appendChild(
                cashFlowsTitle
            );

            card.appendChild(
                cashFlowsList
            );


            try {

                const cashFlows =
                    await loadCashFlows(
                        accessToken,
                        account.id
                    );


                renderCashFlows(
                    cashFlowsList,
                    cashFlows,
                    account,
                    accessToken
                );


            } catch (error) {

                cashFlowsList.className =
                    "error";

                cashFlowsList.textContent =
                    error.message
                    || "입출금 내역을 불러오지 못했습니다.";
            }
            
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
로그인
*/

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


            sessionStorage.setItem(
                "access_token",
                data.access_token
            );


            sessionStorage.setItem(
                "refresh_token",
                data.refresh_token
                || ""
            );


            loginButton.textContent =
                "사용자 확인 중...";


            const user =
                await verifyUser(
                    data.access_token
                );


            loginButton.textContent =
                "계좌 확인 중...";


            const [
                accounts,
                investmentProfile
            ] = await Promise.all([

                loadAccounts(
                    data.access_token
                ),

                loadInvestmentProfile(
                    data.access_token
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
                data.access_token
            );


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
                "block";


        } catch (error) {

            sessionStorage.removeItem(
                "access_token"
            );

            sessionStorage.removeItem(
                "refresh_token"
            );


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
