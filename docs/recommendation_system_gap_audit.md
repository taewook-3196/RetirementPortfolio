# RetirementPortfolio investment recommendation system — gap audit (2026-10-13)

This document records a **source-code review**, not a verified production acceptance test.
Do not interpret percentage estimates as measured completion or investment performance.

## Confirmed on main

| Requested feature | Evidence | Assessment |
|---|---|---|
| Account-based periodic buying and rebalancing | `services/recommendation_service.py` | Implemented foundation; live behavior needs testing |
| Sector momentum | `services/sector_momentum_service.py`, `/api/sector-momentum/{market}` | Preliminary ETF-proxy analytics |
| Relative valuation research | `services/sector_value_screening_service.py`, `/api/sector-value/{market}/{sector}` | Preliminary curated-universe screener, **not** full-universe investment recommendations |
| Market index and asset charts | `/api/market-indices/{index}/chart`, `/api/assets` endpoints | APIs exist; mobile UI and transaction overlays need acceptance tests |
| Watchlist and related news | `/api/watchlist`, `services/news_service.py` | Foundation exists; freshness and ticker matching need verification |
| Morning Kakao reports | `scripts/run_multi_user_morning_reports.py`, `services/daily_report_service.py` | Implemented; independent scheduler/delivery watchdog is not live |

## Priority gaps

1. **Data validity first:** timestamp, currency, financial reporting period, data provenance, stale-price flags, provider failure and missing metric coverage. No fabricated fundamentals.
2. **Explainable equity ranking:** distinguish low PE from undervaluation; normalize by sector; integrate earnings growth, free cash flow, leverage, return on capital and momentum when verifiable. Label missing metrics and suppress unsupported conclusions.
3. **Sector-specific models:** banks (P/B vs ROE and capital), REITs (AFFO), cyclical semiconductors (normalized earnings). The current screener explicitly leaves these as unverified.
4. **Coverage and comparability:** curated ticker sample is not the entire market; disclose selection bias and benchmark sample sizes. Do not call it sector-wide fair value.
5. **Backtesting:** point-in-time fundamentals, transaction costs, survivorship bias, turnover, drawdown, benchmark-relative returns; avoid look-ahead leakage.
6. **User-facing integration:** separate research candidates from personal allocation recommendations; connect rankings and rationale to responsive mobile UI and opt-in report sections.
7. **Operational acceptance:** verify actual API responses, cache TTL, rate limits, user isolation, news relevance, chart transaction markers, and error handling on iOS/Android.
8. **Delivery reliability:** complete PR #161 then dependent PR #162, CI/security review, independent scheduler and administrator alerts after explicit approval.

## Proposed implementation order

- Phase A: data-quality gates, sector screener unit tests, score/rank explanation.
- Phase B: sector-specific valuation and growth/quality indicators.
- Phase C: backtest and evaluation, with benchmark and clear limitations.
- Phase D: mobile UI + watchlist + report integration.
- Phase E: real-device and production read-only acceptance tests.

## Safety and release gates

No automatic trades. Research signals are informational, not guaranteed returns.
Do not deploy, merge draft PRs, create paid services, or send test Kakao messages
without explicit authorization. Preserve production credentials and per-user data isolation.
