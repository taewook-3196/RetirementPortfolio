"""
web/app.py

RetirementPortfolio 모바일 웹 애플리케이션.
"""

from __future__ import annotations

import json
import os

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from supabase import create_client

from database.repository import Repository


app = FastAPI(
    title="RetirementPortfolio",
    version="0.5.0",
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
    """
    Supabase access token을 검증하고
    로그인한 사용자 정보를 반환합니다.
    """

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
    """
    로그인한 사용자의 특정 계좌
    목표 투자 비중을 조회합니다.
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
            detail=(
                "목표 투자 비중을 "
                "불러오지 못했습니다."
            ),
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
                margin: 16px 0 7px;
                font-weight: 600;
            }

            input {
                width: 100%;
                min-height: 48px;
                padding: 12px;
                border: 1px solid #d5d9df;
                border-radius: 10px;
                background: white;
                font-size: 16px;
            }

            button {
                width: 100%;
                min-height: 50px;
                margin-top: 22px;
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

            .targets-title {
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

            .target-loading,
            .target-error {
                padding: 10px 0 2px;
                color: #777;
                font-size: 13px;
            }

            .target-error {
                color: #b3261e;
            }

            .empty {
                padding: 16px 0 4px;
                color: #777;
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


            async function verifyUser(
                accessToken
            ) {
                const response = await fetch(
                    "/api/me",
                    {
                        method: "GET",

                        headers: {
                            "Authorization":
                                "Bearer "
                                + accessToken,
                        },
                    }
                );

                const data =
                    await response.json();

                if (
                    !response.ok
                    || !data.authenticated
                ) {
                    throw new Error(
                        data.detail
                        || "사용자 인증에 실패했습니다."
                    );
                }

                return data;
            }


            async function loadAccounts(
                accessToken
            ) {
                const response = await fetch(
                    "/api/accounts",
                    {
                        method: "GET",

                        headers: {
                            "Authorization":
                                "Bearer "
                                + accessToken,
                        },
                    }
                );

                const data =
                    await response.json();

                if (!response.ok) {
                    throw new Error(
                        data.detail
                        || "계좌 정보를 불러오지 못했습니다."
                    );
                }

                return data.accounts || [];
            }


            async function loadAccountTargets(
                accessToken,
                accountId
            ) {
                const response = await fetch(
                    "/api/accounts/"
                    + accountId
                    + "/targets",
                    {
                        method: "GET",

                        headers: {
                            "Authorization":
                                "Bearer "
                                + accessToken,
                        },
                    }
                );

                const data =
                    await response.json();

                if (!response.ok) {
                    throw new Error(
                        data.detail
                        || "목표 비중을 불러오지 못했습니다."
                    );
                }

                return data.targets || [];
            }


            function createDetail(
                text
            ) {
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
                        "target-loading";

                    empty.textContent =
                        "등록된 목표 ETF가 없습니다.";

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

                    container.appendChild(
                        row
                    );
                }
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
                        "targets-title";

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
                        "targets-list";

                    const loading =
                        document.createElement(
                            "div"
                        );

                    loading.className =
                        "target-loading";

                    loading.textContent =
                        "목표 비중을 불러오는 중...";

                    targetsList.appendChild(
                        loading
                    );

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

                    } catch (error) {
                        targetsList.innerHTML =
                            "";

                        const errorElement =
                            document.createElement(
                                "div"
                            );

                        errorElement.className =
                            "target-error";

                        errorElement.textContent =
                            error.message
                            || (
                                "목표 비중을 "
                                + "불러오지 못했습니다."
                            );

                        targetsList.appendChild(
                            errorElement
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
