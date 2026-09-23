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
    version="0.6.0",
)


@app.get("/health")
def health_check():
    """웹 서버 상태 확인용 API."""

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
            detail=(
                "로그인이 만료되었거나 "
                "유효하지 않습니다."
            ),
        )


def get_verified_user_id(
    authorization: str | None,
) -> str:
    """검증된 로그인 사용자의 user_id를 반환합니다."""

    user = get_current_user(
        authorization=authorization
    )

    return user["user_id"]


@app.get("/api/accounts")
def get_accounts_api(
    authorization: str | None = Header(default=None),
):
    """로그인한 사용자의 계좌만 조회합니다."""

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
                {
                    "id": account.id,
                    "account_name":
                        account.account_name,
                    "account_number":
                        account.account_number,
                    "broker":
                        account.broker,
                    "initial_capital":
                        float(
                            account.initial_capital
                            or 0
                        ),
                    "base_monthly":
                        float(
                            account.base_monthly
                            or 0
                        ),
                    "max_additional_monthly":
                        float(
                            account.max_additional_monthly
                            or 0
                        ),
                    "buy_cycle_type":
                        account.buy_cycle_type,
                    "buy_cycle_detail":
                        account.buy_cycle_detail,
                    "is_default":
                        bool(account.is_default),
                    "memo":
                        account.memo,
                }
                for account in accounts
            ]
        }

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="계좌 정보를 불러오지 못했습니다.",
        )


@app.get(
    "/api/accounts/{account_id}/targets"
)
def get_account_targets_api(
    account_id: int,
    authorization: str | None = Header(default=None),
):
    """특정 계좌의 목표 투자 비중을 조회합니다."""

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


class TransactionCreateRequest(BaseModel):
    """매수/매도 거래 등록 요청."""

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

    quantity: float = Field(
        gt=0,
    )

    price: float = Field(
        ge=0,
    )

    fee: float = Field(
        default=0,
        ge=0,
    )

    tax: float = Field(
        default=0,
        ge=0,
    )

    memo: str = Field(
        default="",
        max_length=1000,
    )


@app.get(
    "/api/accounts/{account_id}/transactions"
)
def get_transactions_api(
    account_id: int,
    authorization: str | None = Header(default=None),
):
    """특정 계좌의 거래 내역을 조회합니다."""

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
    """특정 계좌에 매수/매도 거래를 등록합니다."""

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
            transaction_date=request.transaction_date,
            ticker=request.ticker,
            transaction_type=request.transaction_type,
            quantity=request.quantity,
            price=request.price,
            fee=request.fee,
            tax=request.tax,
            memo=request.memo,
            account_id=account_id,
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
    """특정 계좌의 거래 내역을 수정합니다."""

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

        # tx_id가 실제로 이 계좌에 속하는지 먼저 확인합니다.
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
            transaction_date=request.transaction_date,
            ticker=request.ticker,
            transaction_type=request.transaction_type,
            quantity=request.quantity,
            price=request.price,
            fee=request.fee,
            tax=request.tax,
            memo=request.memo,
            account_id=account_id,
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
    """특정 계좌의 거래 내역을 삭제합니다."""

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

        # 다른 계좌의 거래 ID를 넘겨 삭제하는 것을 막습니다.
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

@app.get(
    "/api/accounts/{account_id}/positions"
)
def get_account_positions_api(
    account_id: int,
    authorization: str | None = Header(default=None),
):
    """특정 계좌의 현재 보유현황을 계산합니다."""

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
            target.ticker: float(
                target.target_weight or 0
            )
            for target in targets
        }

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
            "positions": position_list,
        }

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="보유현황을 계산하지 못했습니다.",
        )

@app.get("/", response_class=HTMLResponse)
def home():
    """모바일 포트폴리오 웹 화면."""

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
                max-width: 520px;
                margin: 20px auto;
            }

            .card {
                background: white;
                border-radius: 18px;
                padding: 24px 20px;
                margin-bottom: 16px;
                box-shadow:
                    0 2px 14px rgba(0, 0, 0, 0.08);
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
                margin: 0 0 24px;
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
                min-height: 72px;
                resize: vertical;
            }

            button {
                width: 100%;
                min-height: 50px;
                margin-top: 18px;
                border: 0;
                border-radius: 10px;
                background: #202124;
                color: white;
                font-size: 16px;
                font-weight: 700;
                cursor: pointer;
            }

            button:disabled {
                opacity: 0.55;
            }

            #message {
                min-height: 24px;
                margin-top: 16px;
                line-height: 1.5;
                font-size: 14px;
            }

            .success {
                color: #137333;
            }

            .error {
                color: #b3261e;
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
                margin-top: 12px;
                padding: 16px;
                border: 1px solid #e1e4e8;
                border-radius: 12px;
                line-height: 1.6;
            }

            .account-name {
                font-size: 18px;
                font-weight: 700;
            }

            .account-detail {
                margin-top: 5px;
                color: #555;
                font-size: 14px;
            }

            .section-title {
                margin-top: 18px;
                padding-top: 15px;
                border-top: 1px solid #eee;
                font-size: 15px;
                font-weight: 700;
            }

            .targets-list {
                margin-top: 8px;
            }

            .target-row {
                display: flex;
                justify-content: space-between;
                gap: 12px;
                padding: 10px 0;
                border-bottom: 1px solid #f0f0f0;
            }

            .target-row:last-child {
                border-bottom: 0;
            }

            .target-info {
                min-width: 0;
            }

            .target-name {
                font-size: 14px;
                font-weight: 600;
                line-height: 1.4;
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

            .transaction-form {
                margin-top: 10px;
                padding: 14px;
                background: #f8f9fa;
                border-radius: 12px;
            }

            .form-row {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 10px;
            }

            .transaction-message {
                min-height: 20px;
                margin-top: 12px;
                font-size: 13px;
                line-height: 1.5;
            }

            .transaction-list {
                margin-top: 8px;
            }

            .transaction-row {
                padding: 11px 0;
                border-bottom: 1px solid #eee;
            }

            .transaction-row:last-child {
                border-bottom: 0;
            }

            .transaction-main {
                display: flex;
                justify-content: space-between;
                gap: 10px;
                font-size: 14px;
                font-weight: 600;
            }

            .transaction-detail {
                margin-top: 3px;
                color: #666;
                font-size: 13px;
            }

            .transaction-actions {
                display: flex;
                gap: 8px;
                margin-top: 9px;
            }
            
            .transaction-actions button {
                width: auto;
                min-height: 36px;
                margin-top: 0;
                padding: 7px 14px;
                font-size: 13px;
            }
            
            .edit-button {
                background: #4b5563;
            }
            
            .delete-button {
                background: #b3261e;
            }
            
            .cancel-button {
                background: #777;
            }
            
            .editing {
                background: #fff8e8;
            }

            .buy {
                color: #b3261e;
            }

            .sell {
                color: #137333;
            }

            .loading,
            .empty {
                padding: 10px 0 2px;
                color: #777;
                font-size: 13px;
                line-height: 1.6;
            }

            .security {
                margin-top: 22px;
                padding-top: 16px;
                border-top: 1px solid #eee;
                color: #777;
                font-size: 13px;
                line-height: 1.6;
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
                    비밀번호 인증은 Supabase Auth가
                    처리하며 포트폴리오 데이터베이스에
                    비밀번호를 저장하지 않습니다.
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


            function formatWon(value) {
                return new Intl.NumberFormat(
                    "ko-KR"
                ).format(
                    Number(value || 0)
                ) + "원";
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
                const date =
                    new Date();

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
            
            
            function renderPositions(
                container,
                positions
            ) {
                container.innerHTML = "";
            
                if (positions.length === 0) {
                    const empty =
                        document.createElement(
                            "div"
                        );
            
                    empty.className = "empty";
                    empty.textContent =
                        "보유현황이 없습니다.";
            
                    container.appendChild(empty);
                    return;
                }
            
                for (const position of positions) {
                    const row =
                        document.createElement(
                            "div"
                        );
            
                    row.className = "target-row";
            
                    const info =
                        document.createElement(
                            "div"
                        );
            
                    info.className = "target-info";
            
                    const name =
                        document.createElement(
                            "div"
                        );
            
                    name.className = "target-name";
                    name.textContent =
                        position.name || position.ticker;
            
                    const ticker =
                        document.createElement(
                            "div"
                        );
            
                    ticker.className = "target-ticker";
                    ticker.textContent =
                        position.ticker;
            
                    const detail =
                        document.createElement(
                            "div"
                        );
            
                    detail.className =
                        "account-detail";
            
                    detail.textContent =
                        "보유 "
                        + formatNumber(
                            position.quantity
                        )
                        + "주 · 평단 "
                        + formatWon(
                            position.average_buy_price
                        );
            
                    info.appendChild(name);
                    info.appendChild(ticker);
                    info.appendChild(detail);
            
                    const cost =
                        document.createElement(
                            "div"
                        );
            
                    cost.className = "target-weight";
                    cost.textContent =
                        formatWon(
                            position.total_buy_cost
                        );
            
                    row.appendChild(info);
                    row.appendChild(cost);
            
                    container.appendChild(row);
                }
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
                    container.textContent =
                        "등록된 목표 ETF가 없습니다.";

                    container.className =
                        "empty";

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

                    container.appendChild(
                        row
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
            
                const targetNameMap = {};
            
                for (const target of targets) {
                    targetNameMap[target.ticker] =
                        target.name;
                }
            
                if (transactions.length === 0) {
                    const empty =
                        document.createElement(
                            "div"
                        );
            
                    empty.className = "empty";
                    empty.textContent =
                        "아직 등록된 거래가 없습니다.";
            
                    container.appendChild(empty);
                    return;
                }
            
                const newestFirst =
                    [...transactions].reverse();
            
                for (const transaction of newestFirst) {
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
                        ] || transaction.ticker;
            
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
                        formatWon(
                            Number(
                                transaction.quantity
                            )
                            * Number(
                                transaction.price
                            )
                        );
            
                    main.appendChild(left);
                    main.appendChild(amount);
            
                    const detail =
                        document.createElement(
                            "div"
                        );
            
                    detail.className =
                        "transaction-detail";
            
                    detail.textContent =
                        "수량 "
                        + formatNumber(
                            transaction.quantity
                        )
                        + " · 체결가 "
                        + formatWon(
                            transaction.price
                        )
                        + " · 수수료 "
                        + formatWon(
                            transaction.fee
                        )
                        + " · 세금 "
                        + formatWon(
                            transaction.tax
                        );
            
                    row.appendChild(main);
                    row.appendChild(detail);
            
                    if (transaction.memo) {
                        const memo =
                            document.createElement(
                                "div"
                            );
            
                        memo.className =
                            "transaction-detail";
            
                        memo.textContent =
                            "메모: "
                            + transaction.memo;
            
                        row.appendChild(memo);
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
            
                    editButton.type = "button";
                    editButton.className =
                        "edit-button";
            
                    editButton.textContent =
                        "수정";
            
                    const deleteButton =
                        document.createElement(
                            "button"
                        );
            
                    deleteButton.type = "button";
                    deleteButton.className =
                        "delete-button";
            
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
                                    + " 거래를 삭제할까요?\\n"
                                    + transaction.transaction_date
                                    + " · "
                                    + typeText
                                    + " · "
                                    + formatNumber(
                                        transaction.quantity
                                    )
                                    + "주"
                                );
            
                            if (!confirmed) {
                                return;
                            }
            
                            deleteButton.disabled =
                                true;
            
                            deleteButton.textContent =
                                "삭제 중...";
            
                            try {
                                const data =
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
            
                                if (!data.deleted) {
                                    throw new Error(
                                        "거래 삭제에 실패했습니다."
                                    );
                                }
            
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
            
                                deleteButton.textContent =
                                    "삭제";
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
                    positions
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
                row.className =
                    "transaction-row editing";
            
                const form =
                    document.createElement(
                        "form"
                    );
            
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
            
                const quantityLabel =
                    document.createElement(
                        "label"
                    );
            
                quantityLabel.textContent =
                    "수량";
            
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
            
                const priceLabel =
                    document.createElement(
                        "label"
                    );
            
                priceLabel.textContent =
                    "체결가격";
            
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
            
                const feeLabel =
                    document.createElement(
                        "label"
                    );
            
                feeLabel.textContent =
                    "수수료";
            
                const feeInput =
                    document.createElement(
                        "input"
                    );
            
                feeInput.type = "number";
                feeInput.min = "0";
                feeInput.step = "any";
                feeInput.value =
                    transaction.fee || 0;
            
                const taxLabel =
                    document.createElement(
                        "label"
                    );
            
                taxLabel.textContent =
                    "세금";
            
                const taxInput =
                    document.createElement(
                        "input"
                    );
            
                taxInput.type = "number";
                taxInput.min = "0";
                taxInput.step = "any";
                taxInput.value =
                    transaction.tax || 0;
            
                const memoLabel =
                    document.createElement(
                        "label"
                    );
            
                memoLabel.textContent =
                    "메모";
            
                const memoInput =
                    document.createElement(
                        "textarea"
                    );
            
                memoInput.value =
                    transaction.memo || "";
            
                const saveButton =
                    document.createElement(
                        "button"
                    );
            
                saveButton.type = "submit";
                saveButton.textContent =
                    "수정 저장";
            
                const cancelButton =
                    document.createElement(
                        "button"
                    );
            
                cancelButton.type = "button";
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
            
                form.appendChild(typeLabel);
                form.appendChild(typeSelect);
                form.appendChild(dateLabel);
                form.appendChild(dateInput);
                form.appendChild(tickerLabel);
                form.appendChild(tickerSelect);
                form.appendChild(quantityLabel);
                form.appendChild(quantityInput);
                form.appendChild(priceLabel);
                form.appendChild(priceInput);
                form.appendChild(feeLabel);
                form.appendChild(feeInput);
                form.appendChild(taxLabel);
                form.appendChild(taxInput);
                form.appendChild(memoLabel);
                form.appendChild(memoInput);
                form.appendChild(saveButton);
                form.appendChild(cancelButton);
                form.appendChild(result);
            
                row.appendChild(form);
            
                cancelButton.addEventListener(
                    "click",
                    async () => {
                        try {
                            await refreshPortfolioData(
                                account,
                                targets,
                                accessToken,
                                transactionsList,
                                positionsList
                            );
            
                        } catch (error) {
                            window.alert(
                                error.message
                                || "거래 내역을 다시 불러오지 못했습니다."
                            );
                        }
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
            
                        result.textContent = "";
            
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
                            const data =
                                await apiRequest(
                                    "/api/accounts/"
                                    + account.id
                                    + "/transactions/"
                                    + transaction.id,
                                    accessToken,
                                    {
                                        method: "PUT",
            
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
            
                            if (!data.updated) {
                                throw new Error(
                                    "거래 수정에 실패했습니다."
                                );
                            }
            
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

                const buyOption =
                    document.createElement(
                        "option"
                    );

                buyOption.value = "BUY";
                buyOption.textContent = "매수";

                const sellOption =
                    document.createElement(
                        "option"
                    );

                sellOption.value = "SELL";
                sellOption.textContent = "매도";

                typeSelect.appendChild(
                    buyOption
                );

                typeSelect.appendChild(
                    sellOption
                );

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
                    todayString();

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

                const quantityLabel =
                    document.createElement(
                        "label"
                    );

                quantityLabel.textContent =
                    "수량";

                const quantityInput =
                    document.createElement(
                        "input"
                    );

                quantityInput.type = "number";
                quantityInput.min = "0.000001";
                quantityInput.step = "any";
                quantityInput.required = true;
                quantityInput.placeholder =
                    "예: 10";

                const priceLabel =
                    document.createElement(
                        "label"
                    );

                priceLabel.textContent =
                    "체결가격";

                const priceInput =
                    document.createElement(
                        "input"
                    );

                priceInput.type = "number";
                priceInput.min = "0";
                priceInput.step = "any";
                priceInput.required = true;
                priceInput.placeholder =
                    "1주당 체결가격";

                const feeLabel =
                    document.createElement(
                        "label"
                    );

                feeLabel.textContent =
                    "수수료";

                const feeInput =
                    document.createElement(
                        "input"
                    );

                feeInput.type = "number";
                feeInput.min = "0";
                feeInput.step = "any";
                feeInput.value = "0";

                const taxLabel =
                    document.createElement(
                        "label"
                    );

                taxLabel.textContent =
                    "세금";

                const taxInput =
                    document.createElement(
                        "input"
                    );

                taxInput.type = "number";
                taxInput.min = "0";
                taxInput.step = "any";
                taxInput.value = "0";

                const memoLabel =
                    document.createElement(
                        "label"
                    );

                memoLabel.textContent =
                    "메모";

                const memoInput =
                    document.createElement(
                        "textarea"
                    );

                memoInput.placeholder =
                    "선택사항";

                const button =
                    document.createElement(
                        "button"
                    );

                button.type = "submit";
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

                form.appendChild(typeLabel);
                form.appendChild(typeSelect);
                form.appendChild(dateLabel);
                form.appendChild(dateInput);
                form.appendChild(tickerLabel);
                form.appendChild(tickerSelect);

                const firstRow =
                    document.createElement(
                        "div"
                    );

                firstRow.className =
                    "form-row";

                const quantityBox =
                    document.createElement(
                        "div"
                    );

                quantityBox.appendChild(
                    quantityLabel
                );

                quantityBox.appendChild(
                    quantityInput
                );

                const priceBox =
                    document.createElement(
                        "div"
                    );

                priceBox.appendChild(
                    priceLabel
                );

                priceBox.appendChild(
                    priceInput
                );

                firstRow.appendChild(
                    quantityBox
                );

                firstRow.appendChild(
                    priceBox
                );

                form.appendChild(firstRow);

                const secondRow =
                    document.createElement(
                        "div"
                    );

                secondRow.className =
                    "form-row";

                const feeBox =
                    document.createElement(
                        "div"
                    );

                feeBox.appendChild(
                    feeLabel
                );

                feeBox.appendChild(
                    feeInput
                );

                const taxBox =
                    document.createElement(
                        "div"
                    );

                taxBox.appendChild(
                    taxLabel
                );

                taxBox.appendChild(
                    taxInput
                );

                secondRow.appendChild(
                    feeBox
                );

                secondRow.appendChild(
                    taxBox
                );

                form.appendChild(secondRow);
                form.appendChild(memoLabel);
                form.appendChild(memoInput);
                form.appendChild(button);
                form.appendChild(result);

                form.addEventListener(
                    "submit",
                    async (event) => {
                        event.preventDefault();

                        result.textContent = "";
                        result.className =
                            "transaction-message";

                        button.disabled = true;
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
                            const data =
                                await apiRequest(
                                    "/api/accounts/"
                                    + account.id
                                    + "/transactions",
                                    accessToken,
                                    {
                                        method: "POST",

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

                            if (!data.created) {
                                throw new Error(
                                    "거래 저장에 실패했습니다."
                                );
                            }

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
                            "초기자금: "
                            + formatWon(
                                account.initial_capital
                            )
                        )
                    );

                    card.appendChild(
                        createDetail(
                            "월 기본 투자금: "
                            + formatWon(
                                account.base_monthly
                            )
                        )
                    );

                    card.appendChild(
                        createDetail(
                            "월 최대 추가 투자금: "
                            + formatWon(
                                account
                                    .max_additional_monthly
                            )
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
                        "targets-list loading";

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

                        targetsList.className =
                            "targets-list";

                        renderTargets(
                            targetsList,
                            targets
                        );

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
                            "targets-list loading";
                        
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
                        
                            positionsList.className =
                                "targets-list";
                        
                            renderPositions(
                                positionsList,
                                positions
                            );
                        
                        } catch (error) {
                            positionsList.className =
                                "error";
                        
                            positionsList.textContent =
                                error.message
                                || "보유현황을 불러오지 못했습니다.";
                        }

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

                        const transactionsTitle =
                            document.createElement(
                                "div"
                            );

                        transactionsTitle.className =
                            "section-title";

                        transactionsTitle.textContent =
                            "거래 내역";

                        const transactionsList =
                            document.createElement(
                                "div"
                            );

                        transactionsList.className =
                            "transaction-list";

                        transactionsList.textContent =
                            "거래 내역을 불러오는 중...";

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
                            transactionsList.innerHTML =
                                "";

                            const errorElement =
                                document.createElement(
                                    "div"
                                );

                            errorElement.className =
                                "error";

                            errorElement.textContent =
                                error.message
                                || (
                                    "거래 내역을 "
                                    + "불러오지 못했습니다."
                                );

                            transactionsList.appendChild(
                                errorElement
                            );
                        }

                    } catch (error) {
                        targetsList.className =
                            "error";

                        targetsList.textContent =
                            error.message
                            || (
                                "목표 비중을 "
                                + "불러오지 못했습니다."
                            );
                    }
                }
            }


            loginForm.addEventListener(
                "submit",
                async (event) => {
                    event.preventDefault();

                    message.textContent = "";
                    message.className = "";

                    loginButton.disabled = true;

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
                                    method: "POST",

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
                            data.refresh_token || ""
                        );

                        loginButton.textContent =
                            "사용자 확인 중...";

                        const user =
                            await verifyUser(
                                data.access_token
                            );

                        loginButton.textContent =
                            "계좌 확인 중...";

                        const accounts =
                            await loadAccounts(
                                data.access_token
                            );

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
