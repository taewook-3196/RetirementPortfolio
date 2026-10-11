"""Read-only sector ETF proxy momentum analytics.

ETF prices are proxies, not official sector index levels.
"""
from datetime import datetime, timedelta, timezone
import math
import time

SECTORS = {
    "us": {
        "technology": ("XLK", "정보기술"), "financials": ("XLF", "금융"),
        "healthcare": ("XLV", "헬스케어"), "industrials": ("XLI", "산업재"),
        "consumer_discretionary": ("XLY", "경기소비재"),
        "consumer_staples": ("XLP", "필수소비재"),
        "energy": ("XLE", "에너지"), "utilities": ("XLU", "유틸리티"),
        "materials": ("XLB", "소재"), "real_estate": ("XLRE", "부동산"),
        "communication": ("XLC", "커뮤니케이션"),
    },
    "kr": {
        "semiconductors": ("091160.KS", "반도체"),
        "banks": ("091170.KS", "은행"),
        "automobiles": ("091180.KS", "자동차"),
        "healthcare": ("244580.KS", "바이오"),
    },
}
BENCHMARKS = {"us": ("SPY", "S&P 500 ETF"), "kr": ("069500.KS", "KOSPI 200 ETF")}
PERIOD_DAYS = {"1m": 30, "3m": 90, "6m": 180, "1y": 365}
_CACHE = {}
_TTL = 900


def _close_history(symbol, start, end):
    import yfinance as yf
    frame = yf.Ticker(symbol).history(
        start=start, end=end, interval="1d", auto_adjust=True, actions=False
    )
    if frame is None or frame.empty:
        raise ValueError("가격 데이터 없음")
    values = []
    for date, row in frame.iterrows():
        price = float(row["Close"])
        if math.isfinite(price) and price > 0:
            values.append((date.date(), price))
    return values


def _return_for_period(values, cutoff):
    if not values or values[-1][0] <= cutoff:
        return None
    # Use the first trading close on or after the period boundary. This
    # avoids requiring a price on a market holiday or non-trading day.
    baseline = next((price for day, price in values if day >= cutoff), None)
    if baseline is None or baseline <= 0:
        return None
    return round((values[-1][1] / baseline - 1) * 100, 2)


def load_sector_momentum(market="us"):
    if market not in SECTORS:
        raise ValueError("지원하지 않는 시장입니다.")
    cached = _CACHE.get(market)
    if cached and time.monotonic() - cached[0] < _TTL:
        return cached[1]
    today = datetime.now(timezone.utc).date()
    end = (today + timedelta(days=1)).isoformat()
    start = (today - timedelta(days=410)).isoformat()
    symbols = {"benchmark": BENCHMARKS[market], **SECTORS[market]}
    histories = {}
    failures = {}
    for key, (ticker, _) in symbols.items():
        try:
            histories[key] = _close_history(ticker, start, end)
        except Exception:
            failures[key] = "가격 조회 실패"
    benchmark = histories.get("benchmark")
    items = []
    for key, (ticker, label) in SECTORS[market].items():
        values = histories.get(key)
        if not values:
            continue
        returns = {
            period: _return_for_period(values, today - timedelta(days=days))
            for period, days in PERIOD_DAYS.items()
        }
        relative = {}
        for period, days in PERIOD_DAYS.items():
            benchmark_return = (
                _return_for_period(benchmark, today - timedelta(days=days))
                if benchmark else None
            )
            relative[period] = (
                round(returns[period] - benchmark_return, 2)
                if returns[period] is not None and benchmark_return is not None else None
            )
        items.append({
            "id": key, "name": label, "ticker": ticker,
            "source_type": "ETF proxy", "returns_pct": returns,
            "relative_pct_points": relative,
            "latest_date": values[-1][0].isoformat(),
        })
    items.sort(key=lambda item: (
        item["returns_pct"]["3m"] is None,
        -(item["returns_pct"]["3m"] or 0),
    ))
    for rank, item in enumerate(items, 1):
        item["rank_3m"] = rank if item["returns_pct"]["3m"] is not None else None
    result = {
        "market": market, "source": "Yahoo Finance (ETF adjusted closes)",
        "benchmark": {"ticker": BENCHMARKS[market][0], "name": BENCHMARKS[market][1]},
        "periods": list(PERIOD_DAYS), "items": items, "failures": failures,
        "as_of": today.isoformat(),
        "disclaimer": "ETF 대용 지표이며 공식 업종지수가 아닙니다. 환율 및 추적오차에 유의하세요.",
    }
    _CACHE[market] = (time.monotonic(), result)
    return result
