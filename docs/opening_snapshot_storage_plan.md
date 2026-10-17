# 계좌 시작 자산 저장 구조 제안 (운영 미적용)

## 데이터 모델

기존 `accounts.initial_capital`을 자동으로 이전하거나 덮어쓰지 않는다. 별도 시작 스냅샷 테이블을 두어 명시적으로 확인한 계좌에만 사용한다.

`account_opening_snapshots`
- `id` bigint PK
- `account_id` bigint FK(accounts.id) ON DELETE CASCADE, UNIQUE
- `opening_date` date NOT NULL
- `currency` text NOT NULL (계좌 기준통화)
- `cash_amount` numeric NOT NULL (0 이상)
- `status` text NOT NULL (`draft` / `confirmed`)
- `created_at`, `updated_at` timestamptz

`account_opening_holdings`
- `id` bigint PK
- `opening_snapshot_id` bigint FK(account_opening_snapshots.id) ON DELETE CASCADE
- `ticker` text NOT NULL
- `quantity` numeric NOT NULL (0 이상)
- `market_value` numeric NOT NULL (0 이상, 스냅샷 기준통화)
- UNIQUE(`opening_snapshot_id`, `ticker`)

스냅샷을 현재 보유종목 계산에 **자동 합산하지 않는다**. 기존 거래 내역에 이미 입력된 시작 보유분과 중복 계산될 위험이 있기 때문이다.

## API 계약 (추후)

- `GET /api/accounts/{id}/opening-snapshot`: 소유권 검사 후 현재 초안/확정값 조회
- `PUT /api/accounts/{id}/opening-snapshot`: 소유권 검사, 원자적 저장, optimistic locking 고려
- `POST /api/accounts/{id}/opening-snapshot/confirm`: 중복 시작 포지션, 거래/입출금 날짜와 평가액 검증 후 확정
- 미설정 계좌에는 `configured: false` 반환, 기존 `initial_capital`을 자동 복사하지 않음

## 전환·정합성 규칙

1. 운영 DB 백업, 롤백 및 적용 전 명시적 승인.
2. 신규 테이블만 추가; 기존 accounts/transactions/cash_flows/dividends의 데이터 수정 금지.
3. `draft`는 성과 계산에 사용하지 않음. `confirmed`도 정확한 시작일/가격/현금흐름 검증 전에는 수익률 계산에 사용하지 않음.
4. 시작일 이전 거래가 있는 계좌는 확인 요청. 초기 보유분과 과거 거래 중복 가능성을 검사.
5. 계좌 통화 변경 시 스냅샷 통화 불일치 경고, 자동 환산 금지.
6. 수익률 계산에 사용하는 시작 총자산은 `cash_amount + SUM(market_value)`. 현재 잔고와 혼동하지 않음.
7. 서버에서는 인증된 사용자 계좌의 소유권을 먼저 확인. 클라이언트가 전달하는 user_id는 신뢰하지 않음.
8. 삭제는 계좌 삭제의 CASCADE에만 연동; 별도 삭제 기능은 감사 로그/복구 정책 설계 후 제공.

## 배포 단계

1. 순수 검증기 및 테스트 (#224) 완료.
2. DB 모델·마이그레이션 파일 및 격리 테스트 (운영 미적용).
3. 인증된 API, 소유권·중복 검증 테스트.
4. 초안 UI, 기존 데이터 확인 안내.
5. 백업/롤백 승인 후 운영 스키마 적용, 소수 계좌에서 검증.
6. 시점별 평가액·거래환율 확보 후 XIRR/TWR 단계적 활성화.
