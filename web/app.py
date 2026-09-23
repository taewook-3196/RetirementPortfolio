"""
web/app.py

RetirementPortfolio 모바일 웹 애플리케이션.
"""


from __future__ import annotations

import os

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from supabase import create_client
from database.repository import Repository


app = FastAPI(
    title="RetirementPortfolio",
    version="0.3.0",
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
    authorization: str | None = Header(
        default=None
    ),
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

    scheme, separator, token = (
        authorization.partition(" ")
    )

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
    """
    검증된 Supabase 로그인 사용자의
    user_id를 반환합니다.
    """

    user = get_current_user(
        authorization=authorization
    )

    return user["user_id"]


@app.get("/api/accounts")
def get_accounts_api(
    authorization: str | None = Header(
        default=None
    ),
):
    """
    로그인한 사용자의 계좌만 조회합니다.
    """

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
                        bool(
                            account.is_default
                        ),

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

@app.get("/", response_class=HTMLResponse)
def home():
    """모바일 로그인 화면."""

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
            <p>
                Supabase 웹 인증 설정이 없습니다.
            </p>
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

        <title>RetirementPortfolio 로그인</title>

        <style>
            * {
                box-sizing: border-box;
            }

            body {
                margin: 0;
                padding: 24px 16px;
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
                max-width: 480px;
                margin: 40px auto;
            }

            .card {
                background: white;
                border-radius: 18px;
                padding: 26px 22px;
                box-shadow:
                    0 2px 14px rgba(0, 0, 0, 0.08);
            }

            h1 {
                margin: 0 0 8px;
                font-size: 25px;
            }

            .subtitle {
                margin: 0 0 26px;
                color: #666;
                line-height: 1.5;
            }

            label {
                display: block;
                margin: 18px 0 7px;
                font-weight: 600;
            }

            input {
                width: 100%;
                min-height: 48px;
                padding: 12px;
                border: 1px solid #d5d9df;
                border-radius: 10px;
                font-size: 16px;
            }

            button {
                width: 100%;
                min-height: 50px;
                margin-top: 24px;
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
                margin-top: 18px;
                line-height: 1.5;
                font-size: 14px;
            }

            .success {
                color: #137333;
            }

            .error {
                color: #b3261e;
            }

            .user-box {
                display: none;
                margin-top: 20px;
                padding: 16px;
                background: #f1f8f4;
                border-radius: 10px;
                line-height: 1.7;
                font-size: 14px;
            }

            .user-box strong {
                display: block;
                margin-bottom: 4px;
            }

            .user-id {
                overflow-wrap: anywhere;
                color: #555;
            }

            .security {
                margin-top: 24px;
                padding-top: 18px;
                border-top: 1px solid #eee;
                color: #777;
                font-size: 13px;
                line-height: 1.6;
            }
        </style>
    </head>

    <body>
        <main class="container">
            <section class="card">

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

                <div
                    id="user-box"
                    class="user-box"
                >
                    <strong>
                        사용자 인증 완료
                    </strong>

                    <div id="user-email"></div>

                    <div
                        id="user-id"
                        class="user-id"
                    ></div>
                </div>

                <div class="security">
                    비밀번호 인증은 Supabase Auth가
                    처리하며 포트폴리오 데이터베이스에
                    비밀번호를 저장하지 않습니다.
                </div>

            </section>
        </main>

        <script>
            const SUPABASE_URL = "__SUPABASE_URL__";
            const SUPABASE_KEY = "__SUPABASE_KEY__";

            const form =
                document.getElementById(
                    "login-form"
                );

            const button =
                document.getElementById(
                    "login-button"
                );

            const message =
                document.getElementById(
                    "message"
                );

            const userBox =
                document.getElementById(
                    "user-box"
                );

            const userEmail =
                document.getElementById(
                    "user-email"
                );

            const userId =
                document.getElementById(
                    "user-id"
                );


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

            form.addEventListener(
                "submit",
                async (event) => {
                    event.preventDefault();

                    message.textContent = "";
                    message.className = "";

                    userBox.style.display =
                        "none";

                    button.disabled = true;

                    button.textContent =
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

                        button.textContent =
                            "사용자 확인 중...";

                        const user =
                            await verifyUser(
                                data.access_token
                            );

                        button.textContent =
                            "계좌 확인 중...";

                        const accounts =
                            await loadAccounts(
                                data.access_token
                            );
                        
                        message.textContent =
                            "로그인 및 사용자 인증에 "
                            + "성공했습니다. "
                            + "등록된 계좌: "
                            + accounts.length
                            + "개";

                        message.className =
                            "success";

                        userEmail.textContent =
                            "이메일: "
                            + (user.email || "");

                        userId.textContent =
                            "사용자 ID: "
                            + user.user_id;

                        userBox.style.display =
                            "block";

                        form.style.display =
                            "none";

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
                        button.disabled = false;

                        button.textContent =
                            "로그인";
                    }
                }
            );
        </script>
    </body>

    </html>
    """

    html = html.replace(
        "__SUPABASE_URL__",
        supabase_url,
    )

    html = html.replace(
        "__SUPABASE_KEY__",
        supabase_key,
    )

    return HTMLResponse(
        content=html
    )
