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

from database.repository import Repository
from portfolio.holdings import calculate_etf_positions


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

        return {
            "account_id": account.id,
            "account_name":
                account.account_name,

            "transactions": [
                {
                    "id":
                        transaction.id,

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
                }
                for transaction
                in transactions
            ],
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

        transactions = repo.get_transactions(
            account_id=account_id
        )

        dividends = repo.get_dividends(
            account_id=account_id
        )

        targets = repo.get_account_targets(
            account_id=account_id
        )

        ticker_names = {
            target.ticker: target.name
            for target in targets
        }

        target_weights = {
            target.ticker:
                float(
                    target.target_weight
                    or 0
                )
            for target in targets
        }

        # 목표종목뿐 아니라 실제 거래종목도 포함합니다.
        for transaction in transactions:
            if transaction.ticker not in ticker_names:
                ticker_names[
                    transaction.ticker
                ] = transaction.ticker

        latest_prices = {}

        for ticker in ticker_names:
            latest_price = repo.get_latest_price(
                ticker
            )

            if latest_price is not None:
                latest_prices[ticker] = (
                    latest_price
                )

        positions = calculate_etf_positions(
            transactions=transactions,
            dividends=dividends,
            latest_prices=latest_prices,
            ticker_names=ticker_names,
        )

        total_current_value = sum(
            float(
                position.current_value
                or 0
            )
            for position in positions.values()
        )

        position_list = []

        for position in positions.values():

            current_value = float(
                position.current_value
                or 0
            )

            if total_current_value > 0:
                current_weight = (
                    current_value
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

                    "quantity":
                        float(
                            position.quantity
                            or 0
                        ),

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
                        current_value,

                    "current_weight":
                        current_weight,

                    "target_weight":
                        target_weights.get(
                            position.ticker,
                            0.0,
                        ),

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
                }
            )

        position_list.sort(
            key=lambda item: item["ticker"]
        )

        return {
            "account_id": account.id,

            "account_name":
                account.account_name,

            "currency":
                account.currency or "KRW",

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

    const response =
        await fetch(
            url,
            {
                ...options,
                headers: headers,
            }
        );

    const data =
        await response.json();

    if (!response.ok) {
        throw new Error(
            data.detail
            || "요청을 처리하지 못했습니다."
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

    return data.positions || [];
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


function renderPositions(
    container,
    positions,
    account
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

    const currency =
        getAccountCurrency(
            account
        );

    for (const position of positions) {

        const row =
            document.createElement(
                "div"
            );

        row.className =
            "transaction-row";

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
                currency
            );

        header.appendChild(name);
        header.appendChild(value);

        row.appendChild(header);

        row.appendChild(
            createDetail(
                position.ticker
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
                    currency
                )
            )
        );

        row.appendChild(
            createDetail(
                "현재가 "
                + formatMoney(
                    position.current_price,
                    currency
                )
                + " · 평가금액 "
                + formatMoney(
                    position.current_value,
                    currency
                )
            )
        );

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
                    currency
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

        row.appendChild(pnl);

        container.appendChild(row);
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

    const currency =
        getAccountCurrency(
            account
        );

    const targetNameMap = {};

    for (const target of targets) {
        targetNameMap[
            target.ticker
        ] = target.name;
    }

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

        const assetName =
            targetNameMap[
                transaction.ticker
            ]
            || transaction.ticker;

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
                currency
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
                    currency
                )
                + " · 수수료 "
                + formatMoney(
                    transaction.fee,
                    currency
                )
                + " · 세금 "
                + formatMoney(
                    transaction.tax,
                    currency
                )
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


async function refreshPortfolioData(
    account,
    targets,
    accessToken,
    transactionsList,
    positionsList
) {
    const [
        transactions,
        positions
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
        account
    );
}


function showTransactionEditor(
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

    const typeLabel =
        document.createElement(
            "label"
        );

    typeLabel.textContent =
        "거래 유형";

    const typeSelect =
        document.createElement(
            "select"
        );

    for (
        const [value, text]
        of [
            ["BUY", "매수"],
            ["SELL", "매도"],
        ]
    ) {
        const option =
            document.createElement(
                "option"
            );

        option.value = value;
        option.textContent = text;

        if (
            transaction.transaction_type
            === value
        ) {
            option.selected = true;
        }

        typeSelect.appendChild(
            option
        );
    }

    const dateLabel =
        document.createElement(
            "label"
        );

    dateLabel.textContent =
        "거래일";

    const dateInput =
        document.createElement(
            "input"
        );

    dateInput.type = "date";
    dateInput.required = true;
    dateInput.value =
        transaction.transaction_date;

    const tickerLabel =
        document.createElement(
            "label"
        );

    tickerLabel.textContent =
        "종목";

    const tickerSelect =
        document.createElement(
            "select"
        );

    for (const target of targets) {

        const option =
            document.createElement(
                "option"
            );

        option.value =
            target.ticker;

        option.textContent =
            target.ticker
            + " · "
            + target.name;

        if (
            target.ticker
            === transaction.ticker
        ) {
            option.selected = true;
        }

        tickerSelect.appendChild(
            option
        );
    }

    /*
    목표 포트폴리오에 없는 기존 거래종목도
    수정 가능하도록 보존합니다.
    */
    if (
        !targets.some(
            target =>
                target.ticker
                === transaction.ticker
        )
    ) {
        const option =
            document.createElement(
                "option"
            );

        option.value =
            transaction.ticker;

        option.textContent =
            transaction.ticker;

        option.selected = true;

        tickerSelect.appendChild(
            option
        );
    }

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
        "종목",
        tickerSelect
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

    const tickerSelect =
        document.createElement(
            "select"
        );

    tickerSelect.required = true;

    for (const target of targets) {

        const option =
            document.createElement(
                "option"
            );

        option.value =
            target.ticker;

        option.textContent =
            target.ticker
            + " · "
            + target.name;

        tickerSelect.appendChild(
            option
        );
    }

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
        "종목",
        tickerSelect
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

    const button =
        document.createElement(
            "button"
        );

    button.type =
        "submit";

    button.textContent =
        "거래 저장";

    if (targets.length === 0) {
        button.disabled = true;
    }

    const result =
        document.createElement(
            "div"
        );

    result.className =
        "transaction-message";

    form.appendChild(button);
    form.appendChild(result);

    form.addEventListener(
        "submit",
        async (event) => {

            event.preventDefault();

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
                    targets.length === 0;

                button.textContent =
                    "거래 저장";
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

    if (accounts.length === 0) {

        const empty =
            document.createElement(
                "div"
            );

        empty.className =
            "empty";

        empty.textContent =
            "아직 등록된 계좌가 없습니다.";

        accountsList.appendChild(
            empty
        );

        return;
    }


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

                const positions =
                    await loadPositions(
                        accessToken,
                        account.id
                    );

                renderPositions(
                    positionsList,
                    positions,
                    account
                );

            } catch (error) {

                positionsList.className =
                    "error";

                positionsList.textContent =
                    error.message
                    || "보유현황을 불러오지 못했습니다.";
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
                true,

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
