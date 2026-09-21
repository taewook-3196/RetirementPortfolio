"""
tests/test_phase4.py
Phase 4 검증 테스트:
- portfolio/holdings.py (이동평균 매수가, 평가손익, 실현손익, 분배금 집계)
- portfolio/performance.py (포트폴리오 전체 종합 성과, 잔여 투자금)
- portfolio/transactions.py (CSV 내보내기 및 가져오기)
"""

import pytest
from pathlib import Path
from database.connection import init_db
from database.repository import Repository
from database.models import Price
from portfolio.holdings import calculate_etf_positions
from portfolio.performance import calculate_portfolio_summary
from portfolio.transactions import TransactionManager


@pytest.fixture
def temp_repo(tmp_path):
    db_file = tmp_path / "portfolio_test.db"
    init_db(db_file)
    return Repository(db_file)


def test_holdings_moving_average_and_pnl(temp_repo):
    """이동평균 매수가 및 매도 실현손익, 평가손익 검증"""
    repo = temp_repo

    # 1. 첫 번째 매수: 100주 @ 10,000원 (수수료 0) -> 평단가 10,000원
    repo.add_transaction("2026-09-01", "442560", "BUY", quantity=100, price=10000)

    # 2. 두 번째 매수: 100주 @ 12,000원 -> 총 200주, 총 2,200,000원 -> 평단가 11,000원
    repo.add_transaction("2026-09-02", "442560", "BUY", quantity=100, price=12000)

    # 3. 일부 매도: 50주 @ 14,000원 매도 -> 실현손익 (14,000 - 11,000) * 50 = +150,000원
    #    남은 보유수량: 150주, 평단가: 11,000원 유지
    repo.add_transaction("2026-09-03", "442560", "SELL", quantity=50, price=14000)

    # 4. 분배금 수령: 20,000원
    repo.add_dividend("2026-09-04", "442560", gross_amount=20000, tax=0, net_amount=20000)

    txs = repo.get_transactions()
    divs = repo.get_dividends()
    latest_prices = {
        "442560": Price(date="20260905", ticker="442560", close_price=13000, name="RISE TDF2040액티브")
    }

    positions = calculate_etf_positions(txs, divs, latest_prices)
    pos = positions["442560"]

    assert pos.quantity == 150
    assert pos.average_buy_price == 11000.0
    assert pos.current_price == 13000.0
    assert pos.current_value == 150 * 13000  # 1,950,000원
    assert pos.total_buy_cost == 150 * 11000  # 1,650,000원
    assert pos.unrealized_pnl == 300000.0   # 1,950,000 - 1,650,000
    assert pos.realized_pnl == 150000.0     # (14,000 - 11,000) * 50
    assert pos.total_dividends == 20000.0
    # 총손익 = 평가손익(30만) + 실현손익(15만) + 분배금(2만) = 470,000원
    assert pos.total_pnl == 470000.0


def test_portfolio_summary_and_remaining_cash(temp_repo):
    """전체 포트폴리오 성과 및 남은 투자금 계산 검증"""
    repo = temp_repo
    repo.add_transaction("2026-09-01", "442560", "BUY", quantity=1000, price=15000)  # 1,500만원
    repo.add_transaction("2026-09-01", "488500", "BUY", quantity=1000, price=10000)  # 1,000만원
    # 총 투자원금 = 2,500만원

    txs = repo.get_transactions()
    divs = repo.get_dividends()
    prices = {
        "442560": Price(date="20260905", ticker="442560", close_price=16000), # +100만원
        "488500": Price(date="20260905", ticker="488500", close_price=10500), # +50만원
    }

    positions = calculate_etf_positions(txs, divs, prices)
    summary = calculate_portfolio_summary(positions, initial_capital=100000000)

    assert summary.total_invested == 25000000.0
    assert summary.total_current_value == (1000 * 16000) + (1000 * 10500)  # 2,650만원
    assert summary.total_unrealized_pnl == 1500000.0
    assert summary.total_pnl == 1500000.0
    # 남은 투자금 = 1억원 - 2,500만원 = 7,500만원
    assert summary.remaining_cash == 75000000.0
    assert summary.position_count == 2


def test_csv_export_import(temp_repo, tmp_path):
    """거래내역 CSV 내보내기 및 가져오기 검증"""
    repo = temp_repo
    tm = TransactionManager(repo)

    repo.add_transaction("2026-09-01", "442560", "BUY", quantity=50, price=15000, memo="테스트")
    export_file = tmp_path / "test_export.csv"
    tm.export_to_csv(export_file)

    assert export_file.exists()
    assert export_file.stat().st_size > 0

    # 신규 빈 DB에 임포트 테스트
    new_db = tmp_path / "import_target.db"
    init_db(new_db)
    new_repo = Repository(new_db)
    new_tm = TransactionManager(new_repo)

    imported_cnt = new_tm.import_from_csv(export_file)
    assert imported_cnt == 1
    imported_tx = new_repo.get_transactions()
    assert len(imported_tx) == 1
    assert imported_tx[0].ticker == "442560"
    assert imported_tx[0].memo == "테스트"
