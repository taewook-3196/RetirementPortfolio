"""
data/mock_provider.py
프롬프트 36번 항목에 정의된 다양한 시장 시나리오(A~H)에 따른 모의(Mock) 가격 데이터를 생성합니다.
A: 모든 ETF 상승
B: TDF -6%
C: S&P500 동일가중 -12%
D: NASDAQ TOP10 -22%
E: 모든 ETF 하락
F: 특정 ETF 목표비중 초과
G: 남은 투자금 부족
H: API 오류
"""

from __future__ import annotations
from datetime import datetime, timedelta
from typing import List, Dict, Any


class MockDataProvider:
    def __init__(self, scenario: str = "normal"):
        self.scenario = scenario.upper()

    def get_historical_prices(
        self,
        tickers: List[Dict[str, str]],
        days: int = 90,
        as_of_date: datetime | None = None,
    ) -> List[Dict[str, Any]]:
        """
        주어진 종목들에 대해 최근 N일간의 일별 모의 가격 데이터를 생성합니다.
        시나리오에 따라 종가 및 3개월 고점 대비 낙폭이 정밀하게 조정됩니다.
        """
        if self.scenario == "H":
            raise ConnectionError("KRX Mock Error: 503 Service Unavailable (Scenario H)")

        end_dt = as_of_date or datetime.now()
        records = []

        base_params = {
            "442560": {"name": "RISE TDF2040액티브", "base": 16400.0},
            "488500": {"name": "TIGER 미국S&P500동일가중", "base": 12400.0},
            "381170": {"name": "TIGER 미국테크TOP10 INDXX", "base": 31500.0},
            "494840": {"name": "TIGER 미국나스닥TOP10", "base": 15000.0},
            "0194T0": {"name": "ACE SK하이닉스단일종목레버리지", "base": 10000.0},
            "494310": {"name": "KODEX 반도체레버리지", "base": 86000.0},
            "233740": {"name": "KODEX 코스닥150레버리지", "base": 6900.0},
            "005930": {"name": "삼성전자", "base": 270000.0},
            "145670": {"name": "ACE 인버스", "base": 1250.0},
            "069500": {"name": "KODEX 200", "base": 35000.0},
        }

        # 시나리오별 최종 낙폭 (Drawdown = current / peak - 1)
        # default / A: peak near current (+0%)
        drawdown_map = {
            "442560": -0.01,
            "488500": -0.02,
            "381170": -0.01,
            "494840": -0.01,
        }
        if self.scenario == "A":
            drawdown_map = {"442560": -0.01, "488500": -0.01, "381170": -0.01, "494840": -0.01}
        elif self.scenario == "B":
            drawdown_map["442560"] = -0.06  # TDF -6%
        elif self.scenario == "C":
            drawdown_map["488500"] = -0.12  # S&P500 동일가중 -12%
        elif self.scenario == "D":
            drawdown_map["381170"] = -0.22  # NASDAQ/Tech TOP10 -22%
            drawdown_map["494840"] = -0.22
        elif self.scenario == "E":
            drawdown_map = {"442560": -0.08, "488500": -0.14, "381170": -0.21, "494840": -0.21}

        for item in tickers:
            ticker = item.get("ticker", "")
            name = item.get("name", base_params.get(ticker, {}).get("name", ticker))
            base_price = base_params.get(ticker, {}).get("base", 15000.0)
            target_dd = drawdown_map.get(ticker, -0.02)

            peak_price = base_price * 1.05
            final_price = peak_price * (1.0 + target_dd)

            for d in range(days, -1, -1):
                dt = end_dt - timedelta(days=d)
                # 주말 제외
                if dt.weekday() >= 5:
                    continue

                date_str = dt.strftime("%Y%m%d")

                # 초반엔 상승하여 고점 형성, 이후 완만히 또는 급격히 하락
                progress = (days - d) / max(days, 1)  # 0.0 ~ 1.0
                if progress < 0.4:
                    # 고점으로 상승
                    price = base_price + (peak_price - base_price) * (progress / 0.4)
                else:
                    # 현재 가격으로 수렴
                    price = peak_price - (peak_price - final_price) * ((progress - 0.4) / 0.6)

                open_p = round(price * 0.998, 0)
                high_p = round(max(price, peak_price if progress >= 0.35 and progress <= 0.45 else price * 1.005), 0)
                low_p = round(price * 0.995, 0)
                close_p = round(price, 0)
                nav = round(close_p * 0.999, 2)

                records.append({
                    "date": date_str,
                    "ticker": ticker,
                    "name": name,
                    "open_price": open_p,
                    "high_price": high_p,
                    "low_price": low_p,
                    "close_price": close_p,
                    "nav": nav,
                    "volume": 15000,
                    "trading_value": int(close_p * 15000),
                })

        return records
