# RetirementPortfolio

모바일 중심 **다중 사용자 퇴직연금·투자 포트폴리오 관리 웹 서비스**입니다.

> 개발 현황, 운영 환경, 완료/예정 작업, 보안 원칙, 인수인계 절차의 **공식 기준 문서**는 [PLAN.md](PLAN.md)입니다. 새 개발자/LLM은 이 파일부터 읽어 주세요.

## 운영 서비스

- 웹: https://retirementportfolio.onrender.com
- 소스/PR: https://github.com/taewook-3196/RetirementPortfolio
- Render: https://dashboard.render.com/web/srv-daprdqad0e5s73a5pbvg
- Supabase: https://supabase.com/dashboard/project/gtwlifmjdfjvkiujzypd
- 작업 계획: [PLAN.md](PLAN.md) · [ROADMAP](docs/ROADMAP.md)

웹 서비스는 인증 기반이며, 실제 계좌·거래·개인 리포트 데이터는 공개하지 않습니다.

## 주요 기능

- 사용자별 계좌·거래·목표 포트폴리오·관심종목 및 관리자 회원관리
- 보유종목 가격 차트와 실제 매수/매도 표시
- 시장지수, 섹터 모멘텀, 기업 상대가치·성장성·수익성·재무건전성 분석
- 사용자별 아침 리포트 및 KakaoTalk 연동
- iPhone, iPad, Android 휴대폰/태블릿 브라우저 사용

기능별 완료·미검증 상태는 [PLAN.md](PLAN.md)를 확인하세요. 섹터 분석은 제한된 표본의 참고 자료로, 투자 권유나 매수 신호가 아닙니다.

## 기술 구성

Python 3.12 · FastAPI · Uvicorn · SQLAlchemy · PostgreSQL (Supabase) · Jinja/JavaScript · yfinance · pytest.

```bash
python -m pip install -r requirements.txt
pytest -q
uvicorn web.app:app --host 0.0.0.0 --port 8000
```

개발용 실행에 필요한 DB/인증 환경변수는 실행 환경에 따라 다릅니다. **실제 비밀번호·토큰을 소스나 문서에 넣지 마세요.** 필요한 환경변수의 이름과 설정 위치는 [PLAN.md의 환경변수 인벤토리](PLAN.md#4-환경변수비밀-설정-인벤토리)를 참고하세요.

Render 운영 배포는 `main` 커밋을 자동 빌드하며, GitHub Actions `.github/workflows/tests.yml`에서 PR마다 `pytest -q`를 실행합니다.

## 아침 리포트

`.github/workflows/morning_report.yml`은 KST 화~토 아침 예약 실행 및 수동 실행을 지원합니다. 실제 발송은 사용자별 활성화·발송 시각·Kakao 인증 상태에 좌우됩니다. 강제 재발송은 실사용자에게 메시지가 전달될 수 있으므로 주의하세요.

## 개발 및 변경 관리

1. `PLAN.md`와 `docs/ROADMAP.md`를 확인하고 현재 `main`/PR/CI/Render 상태를 조회합니다.
2. 별도 브랜치에서 변경하고 관련 회귀 테스트를 작성합니다.
3. PR 자동 테스트 성공 후 병합하고 Render `live`를 확인합니다.
4. **기능 완료·계획 변경·운영 설정 변경 시 같은 작업에서 `PLAN.md`의 상태와 변경 이력을 갱신합니다.**
5. 운영 데이터, 비밀키, OAuth 토큰을 PR·로그·문서에 노출하지 않습니다.

## 구형 데스크톱 코드

초기 Windows Portable/PySide6 앱 관련 코드나 설명이 일부 남아 있을 수 있습니다. **현재 운영 기준은 위 FastAPI 모바일 웹 서비스**이며, 과거 데스크톱 실행 지침을 운영 서버 지침으로 사용하지 마세요.
