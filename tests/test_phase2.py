"""
tests/test_phase2.py
Phase 2 검증 테스트:
- data/mock_provider.py 시나리오별(A, B, C, D, E, H) 데이터 생성
- data/price_updater.py DB 갱신 및 조회
- 3개월 고점 및 Drawdown 수식 정확성 검증
"""

import pytest
from datetime import datetime
from data.mock_provider import MockDataProvider
from data.price_updater import update_market_prices
from database.connection import init_db
from database.repository import Repository
from core.config import get_default_config


def test_mock_scenarios():
    """MockDataProvider 시나리오별 낙폭 검증"""
    tickers = [
        {"ticker": "442560", "name": "RISE TDF2040액티브"},
        {"ticker": "488500", "name": "TIGER 미국S&P500동일가중"},
        {"ticker": "494840", "name": "TIGER 미국나스닥TOP10"},
    ]

    # 시나리오 B: TDF -6%
    mock_b = MockDataProvider(scenario="B")
    data_b = mock_b.get_historical_prices(tickers, days=90)
    assert len(data_b) > 0
    tdf_prices = [p for p in data_b if p["ticker"] == "442560"]
    high_p = max(p["high_price"] for p in tdf_prices)
    latest_p = tdf_prices[-1]["close_price"]
    dd_b = latest_p / high_p - 1.0
    # -6% 부근인지 확인 (허용오차 ±1.5%p)
    assert -0.08 <= dd_b <= -0.04

    # 시나리오 C: S&P500 동일가중 -12%
    mock_c = MockDataProvider(scenario="C")
    data_c = mock_c.get_historical_prices(tickers, days=90)
    sp_prices = [p for p in data_c if p["ticker"] == "488500"]
    high_sp = max(p["high_price"] for p in sp_prices)
    latest_sp = sp_prices[-1]["close_price"]
    dd_c = latest_sp / high_sp - 1.0
    assert -0.15 <= dd_c <= -0.09

    # 시나리오 D: NASDAQ TOP10 -22%
    mock_d = MockDataProvider(scenario="D")
    data_d = mock_d.get_historical_prices(tickers, days=90)
    nasdaq_prices = [p for p in data_d if p["ticker"] == "494840"]
    high_nasdaq = max(p["high_price"] for p in nasdaq_prices)
    latest_nasdaq = nasdaq_prices[-1]["close_price"]
    dd_d = latest_nasdaq / high_nasdaq - 1.0
    assert -0.25 <= dd_d <= -0.18

    # 시나리오 H: API 오류 발생
    mock_h = MockDataProvider(scenario="H")
    with pytest.raises(ConnectionError):
        mock_h.get_historical_prices(tickers)


def test_price_updater_with_mock(tmp_path):
    """Mock 모드 기반 price_updater 실행 및 DB 적재 검증"""
    db_file = tmp_path / "updater_test.db"
    repo = Repository(db_file)
    cfg = get_default_config()
    cfg.data_source = "mock"

    result = update_market_prices(config=cfg, repo=repo, days=60, scenario="B")
    assert result["status"] == "success"
    assert result["saved_count"] > 0

    # DB에 저장된 데이터 확인
    prices = repo.get_prices("442560")
    assert len(prices) > 0
    latest = repo.get_latest_price("442560")
    assert latest is not None
    assert latest.close_price > 0
