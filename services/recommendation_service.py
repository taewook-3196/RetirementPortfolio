"""
services/recommendation_service.py
매수 추천 비즈니스 로직 서비스.
- 최신 시장가, 3개월 최고가, 보유 자산 데이터를 집계
- strategy.recommendation 엔진을 호출하여 이번 달 매수 추천 결과 생성
- 추천 결과를 DB(RecommendationLog)에 저장 및 이전 기록 조회 지원
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional
from core.config import AppConfig, ETFConfig, load_config
from database.repository import Repository
from services.market_data_service import MarketDataService
from services.portfolio_service import PortfolioService
from strategy.recommendation import (
    ETFRecommendationInput,
    ETFRecommendationResult,
    generate_recommendations,
)
from strategy.cycle_helper import check_cycle_investment_history


class RecommendationService:
    def __init__(
        self,
        repo: Repository,
        config: Optional[AppConfig] = None,
        market_service: Optional[MarketDataService] = None,
        portfolio_service: Optional[PortfolioService] = None,
    ):
        self.repo = repo
        self.config = config or load_config()
        self.market_service = market_service or MarketDataService(repo, self.config)
        self.portfolio_service = portfolio_service or PortfolioService(repo, self.config)

    def calculate_recommendations(
        self, account_id: Optional[int] = None, auto_save: bool = True
    ) -> Dict[str, Any]:
        """
        포트폴리오 현황과 시장 가격을 통합하여 최종 매수 추천을 산출합니다.
        account_id 지정 시 해당 계좌의 자산 및 설정 예산을 적용합니다.
        """
        cfg = self.config
        positions = self.portfolio_service.get_positions(account_id=account_id)
        summary = self.portfolio_service.get_summary(positions, account_id=account_id)

        # 계좌별 자본금 한도 및 예산 적용
        already_invested = False
        cycle_desc = ""
        last_buy_dt = None

        if account_id is not None:
            acc = self.repo.get_account(account_id)
            init_cap = int(acc.initial_capital) if acc else cfg.initial_capital
            base_m = int(acc.base_monthly) if acc else cfg.base_monthly
            max_add = int(acc.max_additional_monthly) if acc else cfg.max_additional_monthly

            if acc:
                ctype = getattr(acc, "buy_cycle_type", "monthly")
                cdetail = getattr(acc, "buy_cycle_detail", "25")
                txs = self.repo.get_transactions(account_id=account_id)
                already_invested, last_buy_dt, cycle_desc = check_cycle_investment_history(
                    txs, ctype, cdetail
                )
        else:
            accs = self.repo.get_accounts()
            if accs:
                init_cap = int(sum(a.initial_capital for a in accs))
                base_m = int(sum(a.base_monthly for a in accs))
                max_add = int(sum(a.max_additional_monthly for a in accs))
            else:
                init_cap = cfg.initial_capital
                base_m = cfg.base_monthly
                max_add = cfg.max_additional_monthly

            def_acc = self.repo.get_default_account()
            ctype = getattr(def_acc, "buy_cycle_type", "monthly") if def_acc else "monthly"
            cdetail = getattr(def_acc, "buy_cycle_detail", "25") if def_acc else "25"
            txs = self.repo.get_transactions()
            already_invested, last_buy_dt, cycle_desc = check_cycle_investment_history(
                txs, ctype, cdetail
            )

        target_etfs = self.portfolio_service.get_target_etfs(account_id)
        target_tickers = {e.ticker for e in target_etfs}
        extra_items: List[ETFConfig] = []
        for ticker, pos in positions.items():
            if ticker not in target_tickers and (pos.quantity > 0 or pos.total_buy_cost > 0):
                extra_items.append(ETFConfig(ticker=ticker, name=pos.name or ticker, target_weight=0.0))
        all_etfs = target_etfs + extra_items

        inputs: List[ETFRecommendationInput] = []
        for etf in all_etfs:
            pos = positions.get(etf.ticker)
            cur_price = pos.current_price if pos and pos.current_price > 0 else 0.0
            cur_qty = pos.quantity if pos else 0
            cur_val = pos.current_value if pos else 0.0

            high_price, _ = self.market_service.get_recent_3m_high(etf.ticker)
            if high_price <= 0:
                high_price = cur_price

            inputs.append(
                ETFRecommendationInput(
                    ticker=etf.ticker,
                    name=etf.name,
                    target_weight=etf.target_weight,
                    current_price=cur_price,
                    recent_3m_high=high_price,
                    holding_quantity=cur_qty,
                    current_asset_value=cur_val,
                )
            )

        res = generate_recommendations(
            inputs=inputs,
            initial_capital=init_cap,
            base_monthly=base_m,
            max_additional_monthly=max_add,
            total_invested_so_far=int(summary.total_invested),
            already_invested_in_cycle=already_invested,
            cycle_desc=cycle_desc,
        )

        if auto_save and res.get("recommendations"):
            recs_to_save = [
                {
                    "ticker": r.ticker,
                    "name": r.name,
                    "target_weight": r.target_weight,
                    "current_weight": r.current_weight,
                    "weight_gap": r.weight_gap,
                    "recent_high": r.recent_high,
                    "current_price": r.current_price,
                    "drawdown": r.drawdown,
                    "drawdown_score": r.drawdown_score,
                    "priority_score": r.priority_score,
                    "recommended_buy": r.recommended_buy,
                    "expected_weight_after": r.expected_weight_after,
                    "reason": r.reason,
                }
                for r in res["recommendations"]
            ]
            self.repo.save_recommendations(recs_to_save)

        return res

    def calculate_rebalancing(self, account_id: Optional[int] = None) -> Dict[str, Any]:
        """
        추가 자금 투입 없이 현재 보유 자산을 기준으로 리밸런싱 권장 결과를 산출합니다.
        (고점 대비 5% 이내 유지, 5~20% 낙폭별 추가 매수, 5% 이상 상승 시 절반 익절)
        """
        from strategy.rebalancing import (
            ETFRebalanceInput,
            generate_rebalancing_recommendations,
        )

        cfg = self.config
        positions = self.portfolio_service.get_positions(account_id=account_id)
        summary = self.portfolio_service.get_summary(positions, account_id=account_id)

        target_etfs = self.portfolio_service.get_target_etfs(account_id)
        target_tickers = {e.ticker for e in target_etfs}
        extra_items: List[ETFConfig] = []
        for ticker, pos in positions.items():
            if ticker not in target_tickers and (pos.quantity > 0 or pos.total_buy_cost > 0):
                extra_items.append(ETFConfig(ticker=ticker, name=pos.name or ticker, target_weight=0.0))
        all_etfs = target_etfs + extra_items

        inputs: List[ETFRebalanceInput] = []
        for etf in all_etfs:
            pos = positions.get(etf.ticker)
            cur_price = pos.current_price if pos and pos.current_price > 0 else 0.0
            cur_qty = pos.quantity if pos else 0
            cur_val = pos.current_value if pos else 0.0

            # 직전 3개월 고점 (당일 가격 제외 고점, 미보유 시 일반 고점)
            high_price, _ = self.market_service.get_recent_3m_high(etf.ticker, exclude_today=True)
            if high_price <= 0:
                high_price, _ = self.market_service.get_recent_3m_high(etf.ticker, exclude_today=False)
            if high_price <= 0:
                high_price = cur_price

            inputs.append(
                ETFRebalanceInput(
                    ticker=etf.ticker,
                    name=etf.name,
                    target_weight=etf.target_weight,
                    current_price=cur_price,
                    recent_3m_high=high_price,
                    holding_quantity=cur_qty,
                    current_asset_value=cur_val,
                )
            )

        return generate_rebalancing_recommendations(
            inputs=inputs,
            total_portfolio_value=summary.total_current_value,
        )
