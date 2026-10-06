# RetirementPortfolio Product Roadmap

This document tracks product work that is intentionally scheduled after the current multi-user production stabilization.

## Current priority

1. Complete real new-member E2E after a beta member signs up.
2. Verify Kakao OAuth and immediate test-message delivery with that member.
3. Mobile usability and responsive regression review.
4. Production security/data-integrity regression and v1.0 stabilization.

## Portfolio and chart improvements

- Keep the existing holding detail chart with 1M / 3M / 6M / 1Y / ALL ranges.
- Keep actual BUY / SELL execution markers.
- Improve readability on small mobile screens and when many transaction markers overlap.
- Add index detail charts so major indices can be opened like securities.
  - US: S&P 500, Nasdaq 100 / Composite, Dow, Russell 2000.
  - Korea: KOSPI, KOSDAQ.
  - Include trend context such as moving averages, recent return, and drawdown where data is available.

## Watchlist and personalized news

- Add mobile-web UI to add and remove watchlist securities.
- Store watchlists per user using the existing user-scoped watchlist table.
- Include watchlist symbols in shared market-price collection without leaking one user's watchlist to another.
- Feed the logged-in user's database watchlist into the news/report pipeline instead of relying on global config watchlist entries.
- Include relevant watchlist news in the morning report and Kakao report.
- Visually distinguish held-security news from watchlist news.
- Preserve per-user isolation for watchlists and news context.

## Sector intelligence

### Sector direction report

For Korea and the US, summarize:
- sectors with strengthening upward momentum;
- sectors losing momentum or trending down;
- 1M / 3M / 6M relative performance;
- performance versus the broad market;
- short- and medium-term momentum.

US classification should normally use GICS sectors. Korea should use a stable KRX-compatible industry/sector classification where practical.

### Valuation and candidate screening

Identify sectors worth further review using multiple signals rather than treating a price decline as undervaluation:
- sector-relative valuation;
- earnings/revenue growth;
- profitability and quality;
- balance-sheet strength;
- price momentum and relative strength.

Within attractive sectors, surface representative securities for further review. Results should be framed as research candidates, not guaranteed buy recommendations. Prefer sector-appropriate valuation metrics and expose missing/low-confidence data.

## Data-source constraints

These features are technically feasible. Exact coverage may vary by market-data/news API availability, licensing, rate limits, and fundamentals coverage. If a reliable data source is unavailable, the UI/report must say that the metric is unavailable rather than fabricate it.
