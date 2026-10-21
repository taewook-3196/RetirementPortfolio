# SEC 무료 PBR 데이터 실측 파일럿

목적: 미국 대표 종목 AAPL, MSFT, JNJ의 SEC companyfacts 자기자본·주식수 공시 자료가 PBR BAND 계산에 얼마나 유용한지 검증한다. **검증 전 추천 기능을 활성화하지 않는다.**

## SEC 공식 다운로드 URL

- Apple (AAPL), CIK 0000320193: https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json
- Microsoft (MSFT), CIK 0000789019: https://data.sec.gov/api/xbrl/companyfacts/CIK0000789019.json
- Johnson & Johnson (JNJ), CIK 0000200406: https://data.sec.gov/api/xbrl/companyfacts/CIK0000200406.json

공식 URL에서 받은 JSON을 각각 별도 파일로 저장한다. 회사명이 맞는지 JSON의 entityName, cik 필드로 확인한다. 출처가 불명확한 파일은 실측 성공으로 기록하지 않는다.

## 분석 방법

SEC 이용정책에 따라 실제 연락처가 포함된 User-Agent를 설정한 뒤 제한된 수동 API 호출을 사용한다. API 접근이 차단된 환경에서는 공식 사이트에서 내려받은 JSON을 다음과 같이 분석한다.

```bash
python -m scripts.pilot_sec_companyfacts_offline \
  --file CIK0000320193.json \
  --file CIK0000789019.json \
  --file CIK0000200406.json \
  --as-of 2026-10-21
```

JSON 파일은 Git에 커밋하지 않는다. 결과에서 strict_matches, match_rate_pct, distinct_quarters, span_years, mismatch_reasons를 비교한다. 재무제표 기준일과 공시일을 구분한다. SEC DEI 주식수는 재무제표 말일과 다를 수 있어 매칭률이 낮을 수 있다.

## 합격 기준과 미해결 항목

20개 이상의 서로 다른 보고 분기와 5년 이상의 기간이 확보돼도 **단순 데이터 충족**만 뜻한다. 원본 출처 확인, 지배주주 귀속 보통주 자기자본, 다중 주식 종류, 주식분할/병합 및 당시 시점 가격의 조정 기준, 수정공시·사후 재작성의 시점 일치 여부를 추가 검증해야 한다. 실제 SEC 응답 수집 및 실측 숫자는 아직 미완료.
