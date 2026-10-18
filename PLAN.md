# RetirementPortfolio — PLAN.md (단일 인수인계·운영·개발 기록)

> **최종 갱신: 2026-10-18 KST** · 저장소: `taewook-3196/RetirementPortfolio` · 관리 원칙: **새 채팅/다른 LLM은 이 파일을 먼저 읽고 GitHub/Render/Supabase의 실제 상태를 다시 확인한다.** 이 문서는 개발의 기준점이지만 시시각각 바뀌는 운영 상태의 대체물이 아니다.
>
> **보안 원칙:** 이 파일은 Git에 올라가는 문서다. API 키, 비밀번호, OAuth 토큰, DB 연결 문자열의 자격증명 부분, 회원 개인정보, 실계좌 거래정보는 절대 기재하지 않는다. 환경변수 **이름**, 서비스 식별자, 공개 URL, 설정 경로만 기록한다.

## 0. 새 개발자/LLM 시작 절차 (필독)

1. 이 파일 전체와 `docs/ROADMAP.md`, 현재 `README.md`, 관련 소스·테스트를 읽는다. **README는 PR #274에서 현행 웹 운영 기준으로 개정. 세부 운영 상태는 PLAN.md 및 실제 콘솔 확인.**
2. GitHub `main`의 최신 커밋, 열린 PR, Actions 실행 결과를 확인한다. Render 최근 배포의 `live` 여부와 커밋 일치 여부를 확인한다. Supabase는 **조회 위주**로 프로젝트/스키마를 확인한다.
3. 이 문서의 **진행 중 / 다음 작업 / 미검증** 항목을 실제 코드와 대조해 갱신한다. 이미 구현된 기능을 중복 개발하지 않는다.
4. 별도 작업 브랜치 → 소규모 변경 → 회귀 테스트 → PR → GitHub Actions 성공 확인 → squash merge → Render 자동 배포 `live` 확인 → **동일 PR 또는 후속 문서 PR에서 PLAN.md 갱신** 순서로 진행한다.
5. 사용자의 **“계속 진행하자”는 현재 합의한 작업의 PR 병합·운영 배포 승인까지 포함**한다. 테스트 실패 시 자동 병합 금지. 운영 DB 변경, 계정 삭제, 비밀정보 변경, 실제 카카오 재발송 등 파급력이 큰 작업은 별도 검증·주의가 필요하다.
6. 완료 보고에는 PR URL, 커밋, 테스트 통과 수, Render 배포 상태, 미완료 사항을 **확인한 사실만** 적는다. `build_in_progress`와 `live`를 혼동하지 않는다.

## 1. 목적과 사용자 요구

- 개인 및 복수 사용자 퇴직연금/ISA 등 계좌, 보유자산, 거래, 분배금, 목표 비중, 매수 판단을 **아이폰·아이패드·안드로이드 휴대폰/태블릿**에서 관리하는 인증 기반 웹앱.
- 회원별 계좌·거래·관심종목·설정·뉴스·리포트 완전 분리. 관리자는 가입 허용/중단 및 회원 활성/중지/삭제 관리.
- 계좌별 목표 포트폴리오 설정, 거래 시 미국·한국 종목 검색, 매수·매도 기록과 가격 차트(1M/3M/6M/1Y/ALL 및 BUY/SELL 마커).
- 주요 지수 차트와 섹터 모멘텀, 섹터별 기업 상대가치·성장성·수익성·재무건전성·모멘텀 비교. 분석은 **참고용 후보 선별**이지 매수 권고나 저평가 확정이 아님.
- 관심종목·보유종목 맞춤 뉴스와 한국시간 아침 카카오 리포트. 뉴스는 가능한 **발행 24시간 이내**로 제한(정확한 필터 구현은 코드 재검증).
- 사용자는 불필요한 설명/반복 승인보다 **직접 구현·테스트·결과 보고**를 선호. 유료 한도·GitHub Actions 사용량·Render 무료 플랜 제약 고려.
- 과거 투자금/매수 한도는 개인별 설정으로 관리해야 하며, 오래된 `initial_capital`/`base_monthly` 샘플값을 신규 사용자에게 강제하지 말 것.

## 2. 외부 서비스 및 확인된 설정 (비밀값 제외)

| 구성 | 식별자 / URL | 현재 확인한 사실 / 점검 위치 |
|---|---|---|
| GitHub | https://github.com/taewook-3196/RetirementPortfolio | 기본 브랜치 `main`; PR/Actions 사용 |
| 웹 운영 | https://retirementportfolio.onrender.com | 로그인 필요한 서비스. `/?view=report`는 인증된 리포트 딥링크 |
| Render Dashboard | https://dashboard.render.com/web/srv-daprdqad0e5s73a5pbvg | 서비스 ID `srv-daprdqad0e5s73a5pbvg`; 소유 워크스페이스 `tea-dapr5bc9v7es739l5rig`; 환경 ID `evm-daprdq5g1s2s73d6205g` |
| Render 배포 | 위 대시보드 | `main` 커밋 자동 배포, PR preview 꺼짐, Python 런타임, Singapore 리전, 조회 시 서비스 플랜 `free`, 인스턴스 1개 |
| Render 명령 | 위 대시보드 | build: `pip install -r requirements.txt`; start: `uvicorn web.app:app --host 0.0.0.0 --port $PORT` |
| Supabase 프로젝트 | https://supabase.com/dashboard/project/gtwlifmjdfjvkiujzypd | **StockPortfolio**, 프로젝트 ref `gtwlifmjdfjvkiujzypd`, `ap-northeast-2`(서울), 조회 당시 `ACTIVE_HEALTHY`; PostgreSQL 17. **HanjaLearning 프로젝트 `ehaibfemacjsqzsidlye`와 혼동 금지** |
| Supabase DB 호스트 | `db.gtwlifmjdfjvkiujzypd.supabase.co` | 연결 자격증명은 기록하지 않음. 실제 연결 방식·풀러 포트는 환경 설정에서 확인 |
| Kakao Developers | https://developers.kakao.com | 카카오 OAuth/메시지 권한 및 토큰 연동. 실제 앱 ID/redirect URI/허용 scope는 콘솔과 코드에서 재확인 |
| GitHub Actions | https://github.com/taewook-3196/RetirementPortfolio/actions | `.github/workflows/tests.yml`은 PR/수동 Python 3.12 `pytest -q`; `.github/workflows/morning_report.yml`은 아침 보고서 |
| 시장/AI 소스 | Yahoo Finance (`yfinance`), KRX, BEA, Gemini 등 | 사용 범위/쿼터/자격증명은 소스 및 배포 환경에서 검증. 제공자 장애 시 임의 수치 생성 금지 |

**2026-10-18 마지막 확인 상태:** PR #271까지 `main`에 병합 및 Render `live` 확인(커밋 `ee0a8fefaf7a4605072a5196a715b0a5184b772f`). PR #272도 테스트 성공 후 병합(커밋 `d6cdd050b36ec2fa0a1088916fb187bc916b5872`), **#272 Render `live` 확인(커밋 `d6cdd050b36ec2fa0a1088916fb187bc916b5872`)**. 새 세션에서 반드시 최신 배포를 다시 조회한다. 본 문서 추가 PR의 병합·배포도 별도 확인 필요.

## 3. 기술 구조와 주요 파일

- Python 3.12, FastAPI/`web/app.py`, Uvicorn, SQLAlchemy, PostgreSQL(Supabase), Jinja/인라인 JS 웹 UI, `yfinance`, `cryptography`, `PyJWT`, `pytest`. 실제 의존성은 `requirements.txt` 확인.
- `web/app.py`: 로그인/관리자/계좌/거래/시장분석 화면 및 API. 섹터 API `GET /api/sector-momentum/{market}`, `GET /api/sector-value/{market}/{sector}`; **인증 필수**.
- `database/connection.py`, `database/repository.py` 및 모델/마이그레이션: DB 연결·사용자 스코프·계좌/거래/관심종목/리포트. 운영 스키마·마이그레이션 위치는 실제 저장소 재확인.
- `core/config.py`, `core/public_urls.py`: 환경설정·안전한 공개 URL 및 보고서 링크. 기본 공개 웹 URL은 Render, 리포트 URL은 `/?view=report`. 과거 개인 설정이 기본값으로 유출되지 않도록 주의.
- `services/daily_report_service.py`, `services/kakao_service.py`, `scripts/run_multi_user_morning_reports.py`: 사용자별 보고서 생성·카카오 발송.
- `services/sector_momentum_service.py`: 미국/한국 섹터 ETF·지수 대용 지표의 1M/3M/6M/1Y 추세·상대 수익률; 오래된 시세(7일 초과) 배제.
- `services/sector_value_screening_service.py`: **사전 선정 표본** 기업 재무 비교. 미국 11개 섹터/한국 4개 섹터, 제한된 종목 리스트, 30분 캐시, 최대 4개 동시 조회. `forwardPE` 유효 표본 5개 이상이어야 PER 중앙값을 이용한 비교 가능. 은행/금융/부동산/반도체는 업종별 정책 적용.
- `tests/test_sector_value_screening_service.py` 및 `tests/`: 관련 회귀 테스트. PR 성공 시 최근 약 996개 테스트 통과(건수는 매번 변함).
- `docs/ROADMAP.md`: 기존 기능별 중장기 로드맵. **이 PLAN.md를 최상위 운영 인수인계/변경 이력 문서로 사용**하고, 상세 로드맵과 내용 충돌 시 동기화.
- `README.md`: PR #274에서 현재 모바일 웹 기준으로 개정; 상세 인수인계는 PLAN.md.

## 4. 환경변수/비밀 설정 인벤토리

**값은 이 파일에 기록 금지.** 아래는 코드/워크플로우에서 확인된 **키 이름 또는 운영 시 확인해야 할 항목**이다. 실제로 등록됐는지는 GitHub Settings → Secrets and variables → Actions 및 Render Environment에서 재검증한다.

| 이름 | 용도/확인처 |
|---|---|
| `DATABASE_URL` | PostgreSQL 연결, Render 및 보고서 Actions secret. 절대 전체 URL 기록 금지 |
| `OAUTH_TOKEN_ENCRYPTION_KEY` | 카카오 OAuth 토큰 암호화; Render/Actions 일치 여부 확인. 기존 데이터 암호화 키 임의 교체 금지 |
| `KAKAO_REST_API_KEY` | Kakao Developers REST API 키, OAuth/발송 |
| `KAKAO_ACCESS_TOKEN`, `KAKAO_REFRESH_TOKEN` | `core/config.py`의 레거시/환경변수 지원. 다중 사용자 실제 토큰은 DB 암호화 저장 경로 우선 검증 |
| `KRX_API_KEY` | 한국거래소 데이터 접근 |
| `BEA_API_KEY` | 미국 경제지표 API |
| `GEMINI_API_KEY` | AI 요약/리포트 |
| `GEMINI_MODEL` | AI 모델 선택, Actions variable 또는 환경변수; 코드 기본값은 배포 시점에 재검증 |
| `AI_INVESTMENT_STANCE` | AI 투자 성향 설정 |
| `RETIREMENT_PORTFOLIO_WEB_URL` | 기본 `https://retirementportfolio.onrender.com/` |
| `RETIREMENT_PORTFOLIO_REPORT_URL` | 선택적 호환 override; 기본 `https://retirementportfolio.onrender.com/?view=report` |
| `GITHUB_REPOSITORY`, `GITHUB_TOKEN` | GitHub 실행 문맥/레거시 원격 제어 설정. PAT를 소스나 문서에 넣지 말 것 |
| `PORT` | Render 제공 포트 |
| 기타 로그인/JWT/CORS/관리자 설정 | **정확한 키 이름과 사용 여부는 `web/app.py`, 인증 서비스, Render 환경에서 추가 감사 필요**. 임의 이름을 실제 설정인 것처럼 쓰지 말 것 |

로컬 `.env`, `config.yaml`은 비공개로 취급. `config.example.yaml`은 예제만. GitHub Actions secret, Render secret, Supabase 키는 서로 다른 접근 권한·회전 절차가 있으므로 별도 관리.

## 5. 자동 보고서와 운영 정책

- 확인된 `.github/workflows/morning_report.yml`의 현재 cron:
  - `35 20 * * 1-5` UTC = **화~토 KST 05:35** (다음 날)
  - `10 22 * * 1-5` UTC = **화~토 KST 07:10** (다음 날)
  - `0 0 * * 2-6` UTC = **화~토 KST 09:00** (백업)
- `workflow_dispatch` 수동 실행 및 `force_resend` 입력 지원. 중복 발송 방지·대상 사용자별 설정과 실제 시각은 `scripts/run_multi_user_morning_reports.py` 확인. **수동 강제 재발송은 실제 사용자에게 메시지를 보내므로 사전 주의**.
- 보고서 생성은 사용자별 DB 설정 및 OAuth 권한 기반. Kakao 수신 정상 확인 이력 있음. 7시 정시 도착 보장은 안 됨(GitHub Actions 예약 실행 지연 가능).
- 이전 요구: 화~토 기존 모닝리포트, 일/월 별도 섹터 저평가 후보/대표주 비교 리포트 **아이디어/요구로 기록**. 현재 workflow는 화~토에만 스케줄되어 있으므로 **일/월 보고서 구현·운영 여부 미확인/미완료**.
- 이전에 `morning_report_monitor.yml` 구상/구현 보고가 있었으나 **2026-10-18 `main`에서 해당 경로 404 확인**. 실제 감시 워크플로우가 현재 존재한다고 가정하지 말 것. 과거 로컬 커밋/미푸시 변경 가능성 별도 확인.
- 뉴스 최신성 24시간 제한, 감시/알림, 리포트 차트, 개인별 발송 실패 복구는 **코드·운영 로그로 검증 후 완료 처리**.

## 6. 완료된 주요 개발과 PR 이력

| PR / 시기 | 기능 / 검증된 결과 |
|---|---|
| 초기~2026-10 | PySide6 중심 구상에서 모바일 FastAPI 웹으로 전환, Render/Supabase, 회원가입 관리자 제어, 사용자별 계좌/거래/설정 분리, Kakao 다중 사용자 리포트, 관심종목/뉴스, 차트/시장분석을 단계적으로 구현. 과거 PR 전체 목록은 GitHub에서 확인 |
| #120~#122 | 관리자 경고/감사·요청 실패 복구 관련 수정 이력 |
| #149 | 관심종목·맞춤 뉴스 기능 |
| #261 | 모바일 로그인 문제 수정 |
| #262 | 미국 종목 검색 fallback 및 리터럴 `\\n` 표시 수정 |
| #263 | Yahoo `quoteType` 누락 시 `instrumentType` 기반 ETF 판별, TQQQ 검색 정상 확인 |
| #264 | 오래된 섹터 시세/벤치마크 제외; 병합 `c7aacbb` |
| #265 | 이익 감소 기업 자동 저평가 판정 차단; 병합 `e509a3d` |
| #266 | #264+#265 조합 검증용 임시 **draft PR**, 운영 병합 대상 아님. 상태/종료 여부 재확인 |
| #267 | 재무건전성 위험 신호(일반기업 D/E >300%, 유동비율 <0.8) 시 자동 저평가 보류; 병합 `0bd2ad0` |
| #268 | 은행·금융·부동산에는 일반기업 재무위험 기준 적용 제외; 병합 `fac9189` |
| #269 | 모바일 카드에 성장성/수익성/모멘텀/재무지표 표시; 병합 `b76f6f6` |
| #270 | 사전 지정 섹터 기준 종목 대비 PER/ROE/성장률/마진 비교, 기준 종목은 시총 1위 보장 아님; 병합 `a951ce6` |
| #271 | 종목별 상대가치 판단 근거와 위험·보류 사유 노출; **996 passed, 59 skipped, 29 deselected**, 병합 `ee0a8fe`, Render `live` 확인 |
| #272 | Forward PER 비교 불가 안내 문구 명확화; Actions 성공, 병합 `d6cdd05`; Render `live` 확인 |

섹터 가치평가의 현재 주의사항:
- `UNIVERSE`는 **표본**이며 시장 전체 종목/시총 순위가 아니다. 표본 Forward PER 중앙값은 공식 섹터 평균 PER이 아니다.
- `reasons`에 할인 근거가 있어도 `cautions`에 이익 감소/재무 위험/표본 부족이 있으면 자동 저평가가 아닐 수 있다.
- 금융은 PBR/ROE 참고, 부동산은 P/AFFO 미검증, 반도체는 정규화 이익 미검증. 특수 업종의 일률적 자동 추천 금지.
- Yahoo 재무지표는 누락·지연 가능. 결측치는 `None/null` 유지, 숫자 0으로 대체 금지.
- 일반기업 `debtToEquity`는 Yahoo에서 퍼센트 단위(예: 300=3배)임. 업종별 비교 기준 추가 검토 필요.

## 7. 다음 작업 우선순위 / 미완료·미검증

### P0 — 운영 정확성/보안
- [x] #272 Render `live` 확인(2026-10-18).\n- [ ] 이 문서 PR #273의 CI/Render `live` 확인. 배포 실패 시 로그 확인·수정.
- [ ] 신규 실제 회원 E2E: 가입 허용/중지, 로그인/로그아웃, 회원별 데이터 격리, 계좌·목표비중·거래·관심종목, Kakao OAuth/수신. 실제 계좌 데이터 훼손 없이 테스트.
- [ ] 모바일 iPhone/Android/태블릿: 종목 검색(미국 ETF/주식, 국내 종목), 로그인, 카드 길이, 차트, 입력/저장 후 즉시 갱신, 접근성/대비.
- [ ] Supabase 테이블/인덱스/RLS 또는 서버 사용자 스코프, 관리자 권한, API 인증, 비밀정보 노출, 삭제 cascade, 감사로그, DB 백업/복구 절차 감사.
- [ ] 리포트 발송 로그/시간대/중복 방지, 뉴스 발행 24시간 필터, 장애 모니터링 실제 존재 여부 확인.
- [x] README 웹 운영 구조 문서 개정(PR #274; CI/병합/배포 상태는 확인 필요).

### P1 — 섹터 분석 신뢰도
- [ ] 섹터별 대표 기업 선정 근거 개선: **현재 첫 번째 curated ticker는 시총 1위가 아님**. 시총/유동성/재무지표 신뢰도 확보 후 명시적 대표주 선정, 출처·기준일 노출.
- [ ] 저평가 후보 설명 강화: 성장성/수익성/부채/현금흐름/실적 안정성, 주가 모멘텀을 함께 평가하되 **검증되지 않은 복합 점수로 매수 권고하지 않기**.
- [ ] 섹터별 업종 특화 평가: 금융 PBR/ROE, 부동산 FFO/AFFO, 반도체 사이클 정규화 이익. 데이터가 확보되지 않으면 평가 보류.
- [ ] 종목 비교 UX: 모바일에서 기준 종목/후보를 직접 선택해 나란히 보기, 단위(%, %p, 배) 명확화, 표본/결측/최신성/출처 표시.
- [ ] 미국 11개 섹터·한국 4개 섹터 범위 확대 타당성 및 데이터 제공자 호출 제한/캐시 확인.
- [ ] 섹터 모멘텀/밸류에이션과 아침 리포트 통합 검토(기존 화~토, 일/월 별도 분석 요구는 구현·운영 전 확인).

### P2 — 제품 완성도
- [ ] 계좌별 목표 포트폴리오와 리밸런싱/매수 예산 UX 재검증.
- [ ] 거래가 많을 때 접기·필터·페이지네이션 등 스크롤 부담 감소.
- [ ] 차트 BUY/SELL 마커 중첩, 지수 차트 기간 선택, 오류·빈 데이터 메시지 점검.
- [ ] 시장데이터 장애 대응, 캐시/조회 속도, 사용자별 뉴스 품질과 중복 제거.
- [ ] 무료 요금제 사용량 및 GitHub Actions 제한 고려해 불필요한 빌드/워크플로우 최소화.

## 8. 안전한 검증·배포·롤백 절차

1. `main`에서 최신 브랜치 생성. PR은 작은 기능 단위로 분리.
2. 변경 영향 영역 테스트: `pytest -q` (Python 3.12, `requirements.txt`). 외부 API/실DB/실카카오를 호출하는 테스트는 mock/격리. 인증·사용자 분리·결측/시간대 회귀 테스트 필수.
3. GitHub Actions `Python Tests`가 성공해야 merge. 테스트 성공 숫자만으로 실서비스 동작 보장하지 않으므로 UI/배포 확인 병행.
4. squash merge 후 Render에서 최신 commit ID, build/start 로그, `live`를 확인. 장애 시 마지막 정상 커밋과 변경 PR을 비교하여 안전한 revert PR 또는 Render 롤백 절차 검토.
5. Supabase 스키마 변경은 사전 백업·마이그레이션/역마이그레이션·사용자 데이터 격리 검증 후 시행. 이 파일이나 테스트 코드에 운영 계정·토큰·거래 데이터를 넣지 않는다.
6. **각 완료/계획 변경 시 이 파일의 최종 갱신일, 상태, PR/커밋, 테스트, 배포, 다음 작업, 변경 이력을 갱신한다.** 문서 갱신도 코드 리뷰/CI 흐름에 포함. 다른 LLM이 인수인계할 때 추측한 내용은 반드시 '미확인'으로 표시.

## 9. 변경 기록 (append-only)

| 날짜 (KST) | 변경 | 근거 / 상태 |
|---|---|---|
| 2026-10-18 | 최초 `PLAN.md` 생성. 프로젝트 목표·서비스/프로젝트 ID·환경변수 이름·아키텍처·PR #261~#272·운영 정책·남은 작업·인수인계 절차를 통합 | 이 문서 추가 PR. 최초 작성 후 #272 Render `live` 확인; 문서 PR #273은 검증 중 |
| 2026-10-18 | PR #271 가치평가 근거·주의사항 표시 운영 반영 | CI 996 통과, Render `live` 커밋 `ee0a8fe` 확인 |
| 2026-10-18 | PR #272 Forward PER 안내 문구 수정 병합 | GitHub Actions 성공, squash `d6cdd05`; Render `live` 확인 |

| 2026-10-18 | PR #272 Render 운영 배포 확인 및 문서 PR #273 생성 | #272 Render `live` (`d6cdd05`), 문서 PR https://github.com/taewook-3196/RetirementPortfolio/pull/273 |\n\n| 2026-10-18 | README 구형 데스크톱 설명을 현행 FastAPI 웹 운영 안내로 교체 | PR #274, CI/병합/배포 확인 전 |\n\n**갱신 규칙:** 새 PR을 만들 때 이 문서의 진행 상태를 함께 변경하고, 병합 후 실제 Render `live` 확인 시 완료로 옮긴다. 계획 취소·우선순위 변경·데이터 제공자 변경도 이유와 날짜를 남긴다. GitHub에 없는 로컬 수정이나 미확인 운영 상태를 완료로 표시하지 않는다.
