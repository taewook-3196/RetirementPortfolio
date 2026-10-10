"""Read-only public market index price series for authenticated dashboards."""
from datetime import datetime, timedelta, timezone
import math
import time

INDEX_SYMBOLS = {
    "sp500": ("^GSPC", "S&P 500"),
    "nasdaq100": ("^NDX", "NASDAQ 100"),
    "nasdaq": ("^IXIC", "NASDAQ Composite"),
    "dow": ("^DJI", "Dow Jones"),
    "russell2000": ("^RUT", "Russell 2000"),
    "kospi": ("^KS11", "KOSPI"),
    "kosdaq": ("^KQ11", "KOSDAQ"),
}
PERIOD_DAYS = {"1m": 35, "3m": 100, "6m": 195, "1y": 380, "3y": 1120, "5y": 1850}
_CACHE = {}
_CACHE_SECONDS = 900


def load_index_series(index: str, period: str = "1y") -> dict:
    if index not in INDEX_SYMBOLS:
        raise ValueError("지원하지 않는 지수입니다.")
    if period not in PERIOD_DAYS:
        raise ValueError("지원하지 않는 조회 기간입니다.")
    key = (index, period)
    cached = _CACHE.get(key)
    if cached and time.monotonic() - cached[0] < _CACHE_SECONDS:
        return cached[1]
    import yfinance as yf
    ticker, name = INDEX_SYMBOLS[index]
    end = datetime.now(timezone.utc) + timedelta(days=1)
    start = end - timedelta(days=PERIOD_DAYS[period] + 65)
    frame = yf.Ticker(ticker).history(
        start=start.date().isoformat(), end=end.date().isoformat(),
        interval="1d", auto_adjust=False, actions=False,
    )
    if frame is None or frame.empty:
        raise RuntimeError("지수 가격 데이터를 가져오지 못했습니다.")
    points = []
    closes = []
    for dt, row in frame.iterrows():
        close = float(row["Close"])
        if not math.isfinite(close) or close <= 0:
            continue
        closes.append(close)
        date = dt.strftime("%Y-%m-%d")
        points.append({
            "date": date, "close": round(close, 2),
            "ma20": round(sum(closes[-20:]) / 20, 2) if len(closes) >= 20 else None,
            "ma60": round(sum(closes[-60:]) / 60, 2) if len(closes) >= 60 else None,
        })
    if not points:
        raise RuntimeError("유효한 지수 가격 데이터가 없습니다.")
    first_date = (end - timedelta(days=PERIOD_DAYS[period])).date().isoformat()
    visible = [point for point in points if point["date"] >= first_date]
    if not visible:
        visible = points[-1:]
    first, last = visible[0]["close"], visible[-1]["close"]
    peak, max_drawdown = first, 0.0
    for point in visible:
        peak = max(peak, point["close"])
        max_drawdown = min(max_drawdown, (point["close"] / peak - 1) * 100)
    result = {
        "index": index, "symbol": ticker, "name": name, "period": period,
        "change_pct": round((last / first - 1) * 100, 2),
        "max_drawdown_pct": round(max_drawdown, 2),
        "points": visible,
    }
    if len(_CACHE) > 60:
        _CACHE.clear()
    _CACHE[key] = (time.monotonic(), result)
    return result
