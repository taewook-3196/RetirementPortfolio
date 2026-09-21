"""
tests/test_phase1.py
Phase 1 검증 테스트:
- core/paths.py 포터블 경로 생성 및 확인
- core/config.py 로드, 저장, 유효성 검사
- database/connection.py DB 초기화 및 테이블 생성
- database/repository.py CRUD, 중복 방지, 3개월 고점 조회, SQLite Native Backup/Restore
"""

import pytest
import shutil
from pathlib import Path
from core.paths import get_project_root, ensure_directories
from core.config import load_config, save_config, get_default_config, AppConfig, ETFConfig
from database.connection import init_db, get_db_session
from database.repository import Repository
from database.models import Price, Transaction, Dividend


@pytest.fixture
def temp_db(tmp_path):
    """임시 SQLite DB 경로 및 Repository 픽스처"""
    db_file = tmp_path / "test_portfolio.db"
    init_db(db_file)
    repo = Repository(db_file)
    return repo, db_file


def test_paths(monkeypatch, tmp_path):
    """경로 관리자 동작 및 필수 디렉터리 생성 테스트"""
    root = get_project_root()
    assert root.exists()
    ensure_directories()
    assert (root / "logs").exists()
    assert (root / "backup").exists()
    assert (root / "exports").exists()
    assert (root / "imports").exists()

    # 1. frozen 모드에서 dist 폴더 내부 실행 시: 상위 프로젝트 루트 감지 검증
    fake_proj = tmp_path / "my_project"
    fake_proj.mkdir()
    (fake_proj / "main.py").touch()
    fake_dist_exe = fake_proj / "dist" / "RetirementPortfolio" / "RetirementPortfolio.exe"
    fake_dist_exe.parent.mkdir(parents=True)
    fake_dist_exe.touch()

    import sys
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_dist_exe))
    assert get_project_root() == fake_proj

    # 2. frozen 모드에서 독립 배포 폴더로 외부 복사/이동 시: exe 위치를 독립 루트로 사용 검증
    external_exe = tmp_path / "standalone_app" / "RetirementPortfolio.exe"
    external_exe.parent.mkdir(parents=True)
    external_exe.touch()
    monkeypatch.setattr(sys, "executable", str(external_exe))
    assert get_project_root() == external_exe.parent


def test_config_load_and_validation(tmp_path):
    """config 로드 및 유효성 검증 테스트"""
    cfg_file = tmp_path / "config.yaml"
    cfg = get_default_config()
    assert cfg.initial_capital == 100000000
    assert cfg.base_monthly == 10000000
    assert len(cfg.etfs) == 3

    save_config(cfg, cfg_file)
    loaded = load_config(cfg_file)
    assert loaded.initial_capital == 100000000
    assert loaded.base_monthly == 10000000
    assert loaded.show_splash_screen is True
    assert sum(e.target_weight for e in loaded.etfs) == 1.0

    # 스플래시 화면 비활성화 설정 저장 및 로드 검증
    cfg.show_splash_screen = False
    save_config(cfg, cfg_file)
    reloaded = load_config(cfg_file)
    assert reloaded.show_splash_screen is False

    # 목표 비중 100% 미만 허용 (미설정분은 현금)
    cfg.etfs[0].target_weight = 0.50
    cfg.validate()  # 0.50 + 0.25 + 0.15 = 0.90 -> 정상 통과

    # 목표 비중 합계 100% 초과 시 유효성 오류 발생
    cfg.etfs[0].target_weight = 0.80
    with pytest.raises(ValueError, match="100%를 초과할 수 없습니다"):
        cfg.validate()


def test_watchlist_config_and_validation(tmp_path):
    """관심 종목(Watchlist) 설정 저장, 로드 및 유효성 검증 테스트"""
    from core.config import WatchlistConfig
    cfg_file = tmp_path / "config_watch.yaml"
    cfg = get_default_config()
    cfg.watchlist.append(WatchlistConfig(ticker="102110", name="TIGER 200"))
    save_config(cfg, cfg_file)

    loaded = load_config(cfg_file)
    assert len(loaded.watchlist) == 2
    assert loaded.watchlist[0].ticker == "069500"
    assert loaded.watchlist[1].ticker == "102110"

    # 중복 관심 종목코드 검증
    cfg.watchlist.append(WatchlistConfig(ticker="102110", name="TIGER 200 중복"))
    with pytest.raises(ValueError, match="중복된 관심 종목코드"):
        cfg.validate()


def test_etf_master_repository(temp_db):
    """ETF 마스터 목록 저장 및 실시간 키워드 검색 테스트"""
    repo, _ = temp_db

    # 시드 데이터가 자동 로드되었는지 확인
    results_all = repo.search_etf_master("", limit=200)
    assert len(results_all) > 20

    # 키워드 검색 검증
    results_us = repo.search_etf_master("미국", limit=50)
    assert len(results_us) > 0
    assert any("S&P500" in r["name"] or "나스닥" in r["name"] for r in results_us)

    # 신규 마스터 일괄 저장 검증
    new_master = [
        {"ticker": "999991", "name": "테스트ETF코리아"},
        {"ticker": "999992", "name": "테스트글로벌신재생"},
    ]
    saved = repo.save_etf_master(new_master)
    assert saved == 2

    searched = repo.search_etf_master("테스트ETF", limit=10)
    assert len(searched) == 1
    assert searched[0]["ticker"] == "999991"


def test_repository_prices_and_upsert(temp_db):
    """가격 저장, 중복 방지 및 최근 3개월 고점 계산 테스트"""
    repo, _ = temp_db

    prices_data = [
        {
            "date": "20260901",
            "ticker": "442560",
            "name": "RISE TDF2040액티브",
            "open_price": 15000,
            "high_price": 15500,
            "low_price": 14900,
            "close_price": 15200,
            "nav": 15150,
            "volume": 1000,
            "trading_value": 15200000,
        },
        {
            "date": "20260902",
            "ticker": "442560",
            "name": "RISE TDF2040액티브",
            "open_price": 15200,
            "high_price": 16000,
            "low_price": 15100,
            "close_price": 15900,
            "nav": 15850,
            "volume": 2000,
            "trading_value": 31800000,
        },
        {
            "date": "20260903",
            "ticker": "442560",
            "name": "RISE TDF2040액티브",
            "open_price": 15900,
            "high_price": 15900,
            "low_price": 14800,
            "close_price": 15000,
            "nav": 15000,
            "volume": 1500,
            "trading_value": 22500000,
        },
    ]

    inserted = repo.upsert_prices(prices_data)
    assert inserted == 3

    # 중복 저장 시도 (동일 date, ticker) - 덮어쓰기 확인
    update_data = [
        {
            "date": "20260903",
            "ticker": "442560",
            "name": "RISE TDF2040액티브",
            "open_price": 15900,
            "high_price": 15900,
            "low_price": 14800,
            "close_price": 15100,  # 15000 -> 15100 변경
            "nav": 15050,
            "volume": 1600,
            "trading_value": 24000000,
        }
    ]
    repo.upsert_prices(update_data)
    prices = repo.get_prices("442560")
    assert len(prices) == 3
    assert prices[-1].close_price == 15100

    # 3개월 고점 조회 (최고 종가는 15900)
    high_price, high_date = repo.get_recent_3m_high("442560", as_of_date="20260903")
    assert high_price == 15900
    assert high_date == "20260902"


def test_repository_transactions_and_dividends(temp_db):
    """거래내역 및 분배금 CRUD 테스트"""
    repo, _ = temp_db

    # 1. 거래내역 추가
    tx1 = repo.add_transaction(
        transaction_date="2026-09-01",
        ticker="442560",
        transaction_type="BUY",
        quantity=100,
        price=15000,
        fee=100,
        memo="첫 매수",
    )
    assert tx1.id is not None
    assert tx1.quantity == 100

    # 2. 거래내역 조회
    tx_list = repo.get_transactions("442560")
    assert len(tx_list) == 1

    # 3. 거래내역 수정
    repo.update_transaction(
        tx_id=tx1.id,
        transaction_date="2026-09-01",
        ticker="442560",
        transaction_type="BUY",
        quantity=120,
        price=15000,
        memo="수정 매수",
    )
    updated_tx = repo.get_transactions("442560")[0]
    assert updated_tx.quantity == 120
    assert updated_tx.memo == "수정 매수"

    # 4. 분배금 추가 및 조회
    repo.add_dividend(
        dividend_date="2026-09-10",
        ticker="442560",
        gross_amount=50000,
        tax=7700,
        net_amount=42300,
    )
    div_list = repo.get_dividends("442560")
    assert len(div_list) == 1
    assert div_list[0].net_amount == 42300

    # 5. 거래내역 삭제
    deleted = repo.delete_transaction(tx1.id)
    assert deleted is True
    assert len(repo.get_transactions("442560")) == 0


def test_sqlite_backup_and_restore(temp_db, tmp_path):
    """SQLite Native Backup & Restore 테스트"""
    repo, db_file = temp_db

    # 초기 데이터 삽입
    repo.add_transaction(
        transaction_date="2026-09-01",
        ticker="442560",
        transaction_type="BUY",
        quantity=50,
        price=16000,
    )

    backup_dir = tmp_path / "backup_test"
    backup_path = repo.backup_database(backup_dir)
    assert backup_path.exists()
    assert backup_path.stat().st_size > 0

    # 원본 데이터 삭제
    tx = repo.get_transactions()[0]
    repo.delete_transaction(tx.id)
    assert len(repo.get_transactions()) == 0

    # 복원 수행
    restored = repo.restore_database(backup_path)
    assert restored is True
    assert len(repo.get_transactions()) == 1
