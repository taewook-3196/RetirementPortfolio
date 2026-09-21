"""
tests/test_multi_account.py
다중 계좌(Multi-Account) 및 투자 주기(Buy Cycle) 기능 통합 테스트:
1. 계좌 모델 및 CRUD 검증
2. 매수 주기 계산(cycle_helper) 검증 (none, daily, weekly, biweekly, monthly, bimonthly, quarterly)
3. 계좌별 거래 및 분배금 격리 검증
4. 포트폴리오 성과(PortfolioService) 계좌별/전체통합 계산 검증
5. 매수 추천(RecommendationService) 계좌별 독립 예산 적용 검증
"""

import pytest
from datetime import date
from database.connection import init_db
from database.repository import Repository
from database.models import Account, Transaction, Dividend
from services.portfolio_service import PortfolioService
from services.recommendation_service import RecommendationService
from core.config import get_default_config
from strategy.cycle_helper import calculate_next_investment_date, format_cycle_description


@pytest.fixture
def clean_repo(tmp_path):
    db_file = tmp_path / "test_multi_acc.db"
    init_db(db_file)
    return Repository(db_file)


def test_account_crud_and_default_account(clean_repo):
    repo = clean_repo
    # init_db에서 기본 계좌가 1개 자동 생성되어 있어야 함
    accs = repo.get_accounts()
    assert len(accs) == 1
    assert accs[0].is_default == 1

    # 신규 계좌 2개 추가
    acc2 = repo.create_account(
        account_name="미래에셋 연금저축",
        account_number="201-987-654321",
        broker="미래에셋증권",
        initial_capital=50000000.0,
        base_monthly=5000000.0,
        max_additional_monthly=2000000.0,
        buy_cycle_type="weekly",
        buy_cycle_detail="TUE",
        is_default=0,
        memo="연금저축펀드 계좌",
    )
    assert acc2.id is not None
    assert acc2.account_name == "미래에셋 연금저축"
    assert acc2.buy_cycle_type == "weekly"
    assert acc2.buy_cycle_detail == "TUE"

    acc3 = repo.create_account(
        account_name="토스 일반위탁",
        account_number="301-111-222333",
        broker="토스증권",
        initial_capital=30000000.0,
        base_monthly=2000000.0,
        max_additional_monthly=1000000.0,
        buy_cycle_type="none",
        buy_cycle_detail="",
        is_default=0,
    )

    all_accs = repo.get_accounts()
    assert len(all_accs) == 3

    # 기본 계좌 변경
    repo.set_default_account(acc2.id)
    default_acc = repo.get_default_account()
    assert default_acc.id == acc2.id
    assert default_acc.is_default == 1

    # 계좌 정보 수정
    repo.update_account(
        account_id=acc3.id,
        account_name="토스 ISA 계좌",
        account_number="301-111-999999",
        broker="토스증권",
        initial_capital=40000000.0,
        base_monthly=3000000.0,
        max_additional_monthly=1000000.0,
        buy_cycle_type="monthly",
        buy_cycle_detail="15",
        is_default=0,
    )
    updated_acc3 = repo.get_account(acc3.id)
    assert updated_acc3.account_name == "토스 ISA 계좌"
    assert updated_acc3.buy_cycle_type == "monthly"
    assert updated_acc3.buy_cycle_detail == "15"

    # 계좌 삭제
    repo.delete_account(acc3.id)
    assert len(repo.get_accounts()) == 2
    assert repo.get_account(acc3.id) is None


def test_cycle_helper_calculations():
    fixed_date = date(2026, 9, 18)  # 2026-09-18은 금요일

    # 1. none
    target, diff, text = calculate_next_investment_date("none", "", base_date=fixed_date)
    assert target is None
    assert diff is None
    assert "수동 매수" in text

    # 2. daily (금요일 기준 오늘이 매수일)
    target, diff, text = calculate_next_investment_date("daily", "", base_date=fixed_date)
    assert target == fixed_date
    assert diff == 0
    assert "오늘 매수일" in text

    # 3. weekly TUE (금요일 기준 다음 화요일: 2026-09-22, D-4)
    target, diff, text = calculate_next_investment_date("weekly", "TUE", base_date=fixed_date)
    assert target == date(2026, 9, 22)
    assert diff == 4
    assert "D-4" in text
    assert "화요일" in text

    # 4. monthly 25일 (금요일 기준 9월 25일, D-7)
    target, diff, text = calculate_next_investment_date("monthly", "25", base_date=fixed_date)
    assert target == date(2026, 9, 25)
    assert diff == 7
    assert "D-7" in text
    assert "25일" in text

    # 5. monthly 10일 (9월 10일은 이미 지났으므로 다음달 10월 10일)
    target, diff, text = calculate_next_investment_date("monthly", "10", base_date=fixed_date)
    assert target == date(2026, 10, 10)
    assert diff == (date(2026, 10, 10) - fixed_date).days

    # 6. monthly LAST (9월 말일: 9월 30일)
    target, diff, text = calculate_next_investment_date("monthly", "LAST", base_date=fixed_date)
    assert target == date(2026, 9, 30)
    assert diff == 12


def test_multi_account_portfolio_service(clean_repo):
    repo = clean_repo
    acc1 = repo.get_default_account()
    acc2 = repo.create_account(
        account_name="미래에셋 ISA",
        initial_capital=20000000.0,
        base_monthly=2000000.0,
    )

    cfg = get_default_config()
    p_service = PortfolioService(repo, cfg)

    # 1. acc1에 거래 추가 (442560 10주 @ 10,000)
    repo.add_transaction(
        account_id=acc1.id,
        transaction_date="2026-09-17",
        ticker="442560",
        transaction_type="BUY",
        quantity=10,
        price=10000.0,
    )

    # 2. acc2에 거래 추가 (488500 20주 @ 20,000)
    repo.add_transaction(
        account_id=acc2.id,
        transaction_date="2026-09-17",
        ticker="488500",
        transaction_type="BUY",
        quantity=20,
        price=20000.0,
    )

    # 계좌 1 포지션 확인 (442560만 있어야 함)
    pos_acc1 = p_service.get_positions(account_id=acc1.id)
    assert pos_acc1["442560"].quantity == 10
    assert pos_acc1["488500"].quantity == 0

    # 계좌 2 포지션 확인 (488500만 있어야 함)
    pos_acc2 = p_service.get_positions(account_id=acc2.id)
    assert pos_acc2["442560"].quantity == 0
    assert pos_acc2["488500"].quantity == 20

    # 전체 계좌 통합 확인 (둘 다 있어야 함)
    pos_all = p_service.get_positions(account_id=None)
    assert pos_all["442560"].quantity == 10
    assert pos_all["488500"].quantity == 20

    # 요약 성과 지표(Summary) 검증
    sum_acc1 = p_service.get_summary(pos_acc1, account_id=acc1.id)
    assert sum_acc1.total_invested == 100000.0
    assert sum_acc1.initial_capital == acc1.initial_capital

    sum_acc2 = p_service.get_summary(pos_acc2, account_id=acc2.id)
    assert sum_acc2.total_invested == 400000.0
    assert sum_acc2.initial_capital == acc2.initial_capital

    sum_all = p_service.get_summary(pos_all, account_id=None)
    assert sum_all.total_invested == 500000.0
    # 전체 통합 시 자본금 = acc1.initial_capital + acc2.initial_capital
    assert sum_all.initial_capital == int(acc1.initial_capital + acc2.initial_capital)


def test_multi_account_recommendation_service(clean_repo):
    repo = clean_repo
    acc1 = repo.get_default_account()
    acc2 = repo.create_account(
        account_name="소액 적립식 계좌",
        initial_capital=10000000.0,
        base_monthly=1000000.0,
        max_additional_monthly=500000.0,
    )

    cfg = get_default_config()
    p_service = PortfolioService(repo, cfg)
    r_service = RecommendationService(repo, cfg, portfolio_service=p_service)

    # acc2 기준 매수 추천 산출
    rec_acc2 = r_service.calculate_recommendations(account_id=acc2.id, auto_save=False)
    summary2 = rec_acc2.get("summary", {})
    # acc2의 기본 매수 예산(1,000,000원)이 정확히 반영되어야 함
    assert summary2.get("base_monthly_budget") == 1000000


def test_multi_account_csv_export_import(clean_repo, tmp_path):
    from portfolio.transactions import TransactionManager
    repo = clean_repo
    acc1 = repo.get_default_account()
    acc2 = repo.create_account(
        account_name="신규 계좌",
        initial_capital=30000000.0,
    )

    repo.add_transaction(
        account_id=acc1.id,
        transaction_date="2026-09-17",
        ticker="442560",
        transaction_type="BUY",
        quantity=5,
        price=15000.0,
    )
    repo.add_transaction(
        account_id=acc2.id,
        transaction_date="2026-09-17",
        ticker="488500",
        transaction_type="BUY",
        quantity=8,
        price=12000.0,
    )

    tm = TransactionManager(repo)
    csv_file = tmp_path / "exported_test.csv"
    tm.export_to_csv(csv_file)

    # 새로운 DB에 가져오기 테스트
    new_db = tmp_path / "import_target.db"
    init_db(new_db)
    target_repo = Repository(new_db)
    target_tm = TransactionManager(target_repo)

    imported_cnt = target_tm.import_from_csv(csv_file)
    assert imported_cnt == 2
    imported_txs = target_repo.get_transactions()
    assert len(imported_txs) == 2


def test_account_target_weights(clean_repo):
    """계좌별 독립적인 목표 비중 설정 및 100% 미만(현금 비중) 지원 검증"""
    repo = clean_repo
    acc1 = repo.get_default_account()
    targets1 = repo.get_account_targets(acc1.id)
    assert len(targets1) >= 1

    # 신규 계좌 생성 시 기본 ETF가 자동 복제되었는지 확인
    acc2 = repo.create_account(
        account_name="배당 집중 계좌",
        initial_capital=50000000.0,
    )
    targets2 = repo.get_account_targets(acc2.id)
    assert len(targets2) == len(targets1)

    # acc2의 목표 비중을 70%로 설정 (30%는 미설정 현금)
    from core.config import ETFConfig
    new_targets = [
        ETFConfig(ticker="069500", name="KODEX 200", target_weight=0.40),
        ETFConfig(ticker="488500", name="SOL 미국30년국채", target_weight=0.30),
    ]
    repo.save_account_targets(acc2.id, new_targets)

    # acc2 목표 비중 재조회
    saved2 = repo.get_account_targets(acc2.id)
    assert len(saved2) == 2
    assert round(sum(t.target_weight for t in saved2), 2) == 0.70

    # acc1 목표 비중은 변경 없이 독립적으로 유지되는지 확인
    saved1 = repo.get_account_targets(acc1.id)
    assert len(saved1) == len(targets1)
    assert saved1[0].ticker == targets1[0].ticker


def test_cycle_investment_history_check():
    """모든 매수 주기 유형(monthly, weekly, biweekly, bimonthly, quarterly, daily, none)별 납입 이력 감지 검증"""
    from datetime import date
    from strategy.cycle_helper import check_cycle_investment_history

    base_d = date(2026, 9, 18)  # 금요일, 2026년 9월, 3분기

    # 1. monthly: 당월(9월) 매수 거래 존재 시 True, 전월(8월)은 False
    txs_sept = [{"transaction_type": "BUY", "transaction_date": "2026-09-17"}]
    has_b, _, _ = check_cycle_investment_history(txs_sept, "monthly", "25", base_date=base_d)
    assert has_b is True

    txs_aug = [{"transaction_type": "BUY", "transaction_date": "2026-08-25"}]
    has_b, _, _ = check_cycle_investment_history(txs_aug, "monthly", "25", base_date=base_d)
    assert has_b is False

    # 2. weekly: 이번 주(09-14 월 ~ 09-20 일) 매수 존재 시 True, 지난주(09-11 금)는 False
    txs_this_week = [{"transaction_type": "BUY", "transaction_date": "2026-09-15"}]
    has_b, _, _ = check_cycle_investment_history(txs_this_week, "weekly", "TUE", base_date=base_d)
    assert has_b is True

    txs_last_week = [{"transaction_type": "BUY", "transaction_date": "2026-09-11"}]
    has_b, _, _ = check_cycle_investment_history(txs_last_week, "weekly", "TUE", base_date=base_d)
    assert has_b is False

    # 3. quarterly: 3분기(7~9월) 매수 시 True, 2분기(6월) 매수 시 False
    txs_q3 = [{"transaction_type": "BUY", "transaction_date": "2026-07-10"}]
    has_b, _, _ = check_cycle_investment_history(txs_q3, "quarterly", "25", base_date=base_d)
    assert has_b is True

    txs_q2 = [{"transaction_type": "BUY", "transaction_date": "2026-06-30"}]
    has_b, _, _ = check_cycle_investment_history(txs_q2, "quarterly", "25", base_date=base_d)
    assert has_b is False

    # 4. daily: 오늘(2026-09-18) 매수 시 True, 어제(2026-09-17) 매수 시 False
    txs_today = [{"transaction_type": "BUY", "transaction_date": "2026-09-18"}]
    has_b, _, _ = check_cycle_investment_history(txs_today, "daily", "", base_date=base_d)
    assert has_b is True

    txs_yesterday = [{"transaction_type": "BUY", "transaction_date": "2026-09-17"}]
    has_b, _, _ = check_cycle_investment_history(txs_yesterday, "daily", "", base_date=base_d)
    assert has_b is False

    # 5. none (수동 매수): 항상 False
    has_b, _, _ = check_cycle_investment_history(txs_today, "none", "", base_date=base_d)
    assert has_b is False


def test_recommendation_suppression_on_cycle_buy(clean_repo):
    """주기 내 매수(납입) 이력이 있을 때 추가 매수 금액이 0원으로 추천 제외되는지 검증"""
    from datetime import date
    today_str = date.today().strftime("%Y-%m-%d")

    repo = clean_repo
    acc = repo.get_default_account()
    cfg = get_default_config()

    p_service = PortfolioService(repo, cfg)
    r_service = RecommendationService(repo, cfg, portfolio_service=p_service)

    # 1. 초기 미납입 상태: 이번 주기 납입 이력이 없음
    rec_init = r_service.calculate_recommendations(account_id=acc.id, auto_save=False)
    assert rec_init.get("summary", {}).get("already_invested_in_cycle") is False

    # 2. 당월 매수 거래 추가 -> 납입 완료 상태로 전환
    repo.add_transaction(
        account_id=acc.id,
        transaction_date=today_str,
        ticker="442560",
        transaction_type="BUY",
        quantity=100,
        price=15000.0,
    )

    rec = r_service.calculate_recommendations(account_id=acc.id, auto_save=False)
    summary = rec.get("summary", {})
    assert summary.get("already_invested_in_cycle") is True
    assert summary.get("total_additional_buy") == 0

    # 각 종목의 추가 매수금도 0원이어야 함
    for r in rec.get("recommendations", []):
        assert r.additional_buy == 0

    # 3. 신규 미납입 계좌 생성 시: 미납입 상태이므로 already_invested_in_cycle이 False
    acc_fresh = repo.create_account(
        account_name="신규 미납입 계좌",
        initial_capital=50000000.0,
        base_monthly=5000000.0,
        max_additional_monthly=3000000.0,
        buy_cycle_type="monthly",
    )
    rec_fresh = r_service.calculate_recommendations(account_id=acc_fresh.id, auto_save=False)
    sum_fresh = rec_fresh.get("summary", {})
    assert sum_fresh.get("already_invested_in_cycle") is False


