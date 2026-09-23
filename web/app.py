"""
web/app.py

RetirementPortfolio 모바일 웹 애플리케이션의 시작점.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse


app = FastAPI(
    title="RetirementPortfolio",
    version="0.1.0",
)


@app.get("/health")
def health_check():
    """웹 서버 상태 확인용 API."""
    return {
        "status": "ok",
        "service": "RetirementPortfolio",
    }


@app.get("/", response_class=HTMLResponse)
def home():
    """모바일 웹 첫 화면."""
    return """
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
                max-width: 520px;
                margin: 0 auto;
            }

            .card {
                background: white;
                border-radius: 16px;
                padding: 24px;
                box-shadow:
                    0 2px 12px rgba(0, 0, 0, 0.08);
            }

            h1 {
                margin: 0 0 8px;
                font-size: 24px;
            }

            .subtitle {
                margin: 0 0 24px;
                color: #666;
                line-height: 1.5;
            }

            .status {
                padding: 16px;
                border-radius: 12px;
                background: #f0f4f8;
                line-height: 1.6;
            }

            .next {
                margin-top: 20px;
                font-size: 14px;
                color: #666;
                line-height: 1.6;
            }
        </style>
    </head>

    <body>
        <main class="container">
            <section class="card">
                <h1>RetirementPortfolio</h1>

                <p class="subtitle">
                    스마트폰·태블릿용
                    포트폴리오 관리 서비스
                </p>

                <div class="status">
                    웹 애플리케이션이 정상적으로
                    실행되고 있습니다.
                </div>

                <div class="next">
                    다음 단계에서 로그인과
                    계좌 관리 화면을 연결합니다.
                </div>
            </section>
        </main>
    </body>
    </html>
    """
