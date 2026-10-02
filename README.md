# 개인 퇴직연금 ETF 포트폴리오 관리 및 월간 매수 의사결정 지원 프로그램

Windows PC에서 실행되는 **Portable(휴대용) 데스크톱 프로그램**입니다.  
별도의 DB 서버(MariaDB, MySQL 등)나 웹서버 설치 없이 **프로그램 폴더 하나만 복사**하여 어디서든 실행할 수 있습니다.

---

## 1. 주요 특징

- **100% Portable 구조**: 프로그램 폴더 전체를 외장 드라이브, 다른 PC, 한글/공백 경로로 이동해도 설정과 DB가 그대로 유지됩니다.
- **SQLite 단일 파일 관리**: 모든 가격 데이터, 거래내역, 분배금, 설정 기록이 `portfolio.db` 파일 하나에 안전하게 저장됩니다.
- **한국거래소(KRX) 공식 Open API 연동**: ETF 실시간 시세, NAV, 거래량, 거래대금 데이터를 정식 연동합니다.
- **전략적 분할 매수 의사결정 모델**:
  - 사용자가 설정한 월 기본 매수 한도를 목표비중에 맞추어 배분
  - 최근 가격 대비 하락폭(Drawdown)과 사용자 설정에 따라 추가매수 후보 산출
  - 계좌별 현금과 사용자 설정 한도 내에서 매수 예산 계산
  - 목표비중 초과 종목 추가매수 자동 제한
  - 자연어 매수 추천 사유 자동 생성
- **PySide6 기반 모던 GUI**:
  - 6대 메인 화면: 대시보드, 포트폴리오, 매수추천, 거래내역, 시장데이터, 환경설정
  - QThread 비동기 작업자로 대용량 데이터 갱신 시에도 UI 멈춤 현상 없음
  - Matplotlib 내장 자산 배분 도넛 차트 및 3개월 가격 추이 차트

---

## 2. 폴더 구조

```
RetirementPortfolio/
├── RetirementPortfolio.exe   # 단일 실행 파일 (onedir 빌드 시)
├── config.example.yaml       # 공개 가능한 설정 예제 (개인 config.yaml은 Git 제외)
├── portfolio.db              # SQLite 데이터베이스 파일
├── README.md                 # 프로그램 설명서
├── .env                      # KRX API 키 (보안 보관)
├── logs/                     # 실행 및 에러 로그 (app.log, error.log)
├── backup/                   # DB 안전 백업 파일 저장소
├── exports/                  # CSV 내보내기 폴더
└── imports/                  # CSV 가져오기 폴더
```

---

## 3. 개발 및 실행 방법

### 3.1 개발 환경 실행 (Python)

```bash
# 의존성 설치
pip install -r requirements.txt

# GUI 실행
python main.py

# 백그라운드/작업 스케줄러 시장 데이터 수집 CLI
python -m data.price_updater

# 단위 및 통합 테스트 실행 (19개 테스트)
pytest -v tests/
```

### 3.2 KRX OPEN API 설정

1. [KRX OPEN API 홈페이지](https://openapi.krx.co.kr/)에서 무료 회원가입 및 API 인증키 발급
2. 서비스 목록에서 **증권상품 > ETF 일별매매정보** [API 이용신청] 완료
3. 프로그램 루트 폴더의 `.env` 파일에 발급받은 키 입력:
   ```env
   KRX_API_KEY=your_krx_api_key
   ```

### 3.3 개인 설정 파일 준비

저장소의 `config.example.yaml`을 복사해 로컬에서 `config.yaml`을 만든 뒤 개인 설정을 입력합니다.

```bash
cp config.example.yaml config.yaml
```

`config.yaml`은 Git 추적에서 제외됩니다. API 키, 토큰, 비밀번호 같은 비밀값은 저장소에 커밋하지 말고 환경변수 또는 GitHub Secrets를 사용하세요.

### 3.4 공개 Web 및 Morning Report URL 설정

배포 환경에서는 다음 환경변수(또는 GitHub Actions의 같은 이름인 Repository Variable)를 설정할 수 있습니다.

```env
RETIREMENT_PORTFOLIO_WEB_URL=https://retirementportfolio.onrender.com/
RETIREMENT_PORTFOLIO_REPORT_URL=https://retirementportfolio.onrender.com/?view=report
```

- `RETIREMENT_PORTFOLIO_WEB_URL`은 포트폴리오 관리 deep link에 사용됩니다.
- `RETIREMENT_PORTFOLIO_REPORT_URL`은 호환용 override이며 반드시 인증된 Render 리포트 화면을 가리켜야 합니다.
- 두 값은 공개 `http`/`https` URL만 허용하며, 잘못된 scheme 또는 hostname 없는 값은 안전한 기본 URL로 대체됩니다.
- override가 없으면 `RETIREMENT_PORTFOLIO_WEB_URL`의 `?view=report` 화면을 사용합니다. GitHub Pages fallback은 개인 금융정보 공개를 막기 위해 지원하지 않습니다.

### 3.5 Mock 시뮬레이션 모드 (네트워크 없는 환경)

`config.yaml` 파일에서 `data_source`를 `mock`으로 변경하거나 GUI의 [환경 설정] 화면에서 변경할 수 있습니다:
```yaml
data_source: mock
```

---

## 4. 데이터베이스 백업 및 복원 방법

### 4.1 백업 방법
1. 프로그램 실행 후 좌측 메뉴의 **[⚙️ 환경 설정]** 클릭
2. **[📦 데이터베이스 백업 생성]** 버튼 클릭
3. `backup/portfolio_YYYYMMDD_HHMMSS.db` 형태로 SQLite Native Backup API를 통해 안전하게 백업 파일이 생성됩니다.

### 4.2 복원 방법
- **GUI에서 복원**: [환경 설정] 화면에서 **[🔄 백업 파일로 복원]** 버튼을 누르고 복원할 `.db` 파일을 선택합니다.
- **수동 복원**: 프로그램을 종료한 후, `backup/` 폴더 내의 원하는 백업 파일을 프로그램 루트 폴더의 `portfolio.db`로 파일명을 변경하여 덮어쓰기 합니다.

---

## 5. Portable EXE 빌드 방법 (PyInstaller)

```bash
pyinstaller --noconsole --onedir --name RetirementPortfolio main.py
```

빌드 완료 후 생성된 `dist/RetirementPortfolio` 폴더에 `config.yaml`, `.env`, `portfolio.db`를 함께 복사하여 배포하면 단일 폴더 이동만으로 어떤 PC에서도 즉시 실행 가능합니다.
