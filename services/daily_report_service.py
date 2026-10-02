"""
services/daily_report_service.py
일일 모닝 리포트 생성 및 카카오톡 자동 발송 오케스트레이터.
- 포트폴리오 현황, 매수 추천(AI 가이드), 관심/보유 종목 뉴스 집계
- 반응형 모바일 HTML 리포트 자동 생성 (services/report_html_generator.py)
- 카카오톡 요약 피드 및 웹 링크 발송 (services/kakao_service.py)
- CLI / Windows 작업 스케줄러를 통한 백그라운드 단독 실행 지원
"""

from __future__ import annotations
import os
import sys
import logging
import datetime
from datetime import date
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from core.config import (
    AppConfig,
    MorningReportConfig,
    ETFConfig,
    get_report_url,
    get_web_app_url,
    load_config,
    validate_public_url,
)
from core.paths import get_project_root, get_report_dir
from database.connection import init_db
from database.repository import Repository
from services.portfolio_service import PortfolioService
from services.recommendation_service import RecommendationService
from services.news_service import NewsService
from services.report_html_generator import ReportHtmlGenerator
from services.kakao_service import KakaoService
from services.gemini_service import GeminiService
from services.macro_indicator_service import MacroIndicatorService
from strategy.cycle_helper import calculate_next_investment_date

logger = logging.getLogger("RetirementPortfolio.DailyReportService")


class DailyReportService:
    """일일 모닝 리포트 생성 및 발송 서비스"""

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        repo: Optional[Repository] = None,
    ):
        self.config = config or load_config()
        
        if repo is not None:
            self.repo = repo
        else:
            report_user_id = os.getenv(
                "REPORT_USER_ID",
                "",
            ).strip()
        
            if not report_user_id:
                raise RuntimeError(
                    "REPORT_USER_ID 환경변수가 설정되지 않았습니다."
                )
        
            self.repo = Repository(
                user_id=report_user_id
            )
        
        self.portfolio_service = PortfolioService(
            self.repo,
            self.config,
        )
        self.recommendation_service = RecommendationService(self.repo, self.config, portfolio_service=self.portfolio_service)
        self.news_service = NewsService()
        self.html_generator = ReportHtmlGenerator(self.config.morning_report)
        self.kakao_service = KakaoService.for_user(self.config, self.repo)
        self.gemini_service = GeminiService(self.config)
        self.macro_service = MacroIndicatorService()

    def _attach_report_chart_data(
        self,
        account_groups: List[Dict[str, Any]],
        price_limit: int = 260,
    ) -> None:
        """정적 보고서용 공개 가능 차트 데이터만 종목에 연결합니다."""
        for group in account_groups:
            account_id = group.get("account_id")
            if account_id is None:
                continue

            for position in group.get("positions", []) or []:
                ticker = str(position.get("ticker", "")).strip().upper()
                position["chart_data"] = {"prices": [], "transactions": []}
                if not ticker:
                    continue

                try:
                    raw = self.repo.get_asset_chart_data(
                        account_id=int(account_id),
                        ticker=ticker,
                        limit=price_limit,
                    ) or {}

                    prices = []
                    for item in (raw.get("prices", []) or [])[-price_limit:]:
                        prices.append({
                            "date": str(item.get("date", "")),
                            "open": float(item.get("open", 0) or 0),
                            "high": float(item.get("high", 0) or 0),
                            "low": float(item.get("low", 0) or 0),
                            "close": float(item.get("close", 0) or 0),
                        })

                    first_date = prices[0]["date"] if prices else ""
                    transactions = []
                    for item in raw.get("transactions", []) or []:
                        tx_date = str(item.get("date", ""))
                        tx_type = str(item.get("type", "")).strip().upper()
                        if tx_type not in ("BUY", "SELL"):
                            continue
                        if first_date and tx_date < first_date:
                            continue
                        transactions.append({
                            "date": tx_date,
                            "type": tx_type,
                            "price": float(item.get("price", 0) or 0),
                            "quantity": float(item.get("quantity", 0) or 0),
                        })

                    position["chart_data"] = {
                        "prices": prices,
                        "transactions": transactions[-200:],
                    }
                except Exception:
                    logger.warning(
                        "보고서 차트 데이터 준비 실패 (%s/%s)",
                        account_id,
                        ticker,
                    )

    @staticmethod
    def _format_money(
        value: Any,
        currency: str = "KRW",
    ) -> str:
        """
        계좌 기준 통화에 맞춰 금액을 표시합니다.

        KRW: 1,000,000원
        USD: $1,000.00
        """
        try:
            amount = float(value or 0)
        except (TypeError, ValueError):
            amount = 0.0

        currency_code = str(
            currency or "KRW"
        ).strip().upper()

        if currency_code == "USD":
            return f"${amount:,.2f}"

        if currency_code == "KRW":
            return f"{amount:,.0f}원"

        return (
            f"{amount:,.2f} "
            f"{currency_code}"
        )

    def _build_overall_portfolio_summary(
        self,
        portfolio_summary,
    ) -> Dict[str, float]:
        """검증된 전체 PortfolioSummary를 보고서 필드로 변환합니다."""
        stock_eval = float(portfolio_summary.total_current_value or 0)
        cash_balance = float(portfolio_summary.remaining_cash or 0)
        total_assets = stock_eval + cash_balance

        return {
            # total_eval은 기존 HTML/외부 소비자 호환 별칭입니다.
            "total_eval": total_assets,
            "total_assets": total_assets,
            "stock_eval": stock_eval,
            "cash_balance": cash_balance,
            "total_cost": float(portfolio_summary.total_invested or 0),
            "total_pl": float(portfolio_summary.total_pnl or 0),
            "total_pl_pct": float(portfolio_summary.total_roi or 0) * 100.0,
        }

    def _generate_ai_analysis(
        self,
        context: Dict[str, Any],
        enabled: bool,
    ) -> Dict[str, Any]:
        """AI 실패를 보고서 전체 실패와 격리합니다."""
        if not enabled:
            return {}

        try:
            return self.gemini_service.generate_macro_investment_guide(
                context
            )
        except Exception as exc:
            logger.warning(
                "AI 분석을 생성하지 못해 대체 안내를 사용합니다: %s",
                type(exc).__name__,
            )
            return self.gemini_service.build_fallback_response(
                "AI 분석 생성 예외"
            )

    def generate_and_send(
        self,
        send_kakao: bool = True,
        update_prices: bool = True,
        force_kakao: bool = False,
    ) -> Tuple[bool, str, Optional[Path]]:
        """
        리포트 데이터를 집계하여 HTML 리포트를 생성하고,
        옵션에 따라 카카오톡 요약 및 웹 링크를 발송합니다.
        
        매일 아침 발송 전 최신 시장 가격(전일 종가 등)을 KRX Open API로부터 자동 수신하여 DB를 최신화합니다.
        
        반환값: (성공 여부, 결과 메시지, 생성된 HTML 파일 경로)
        """
        try:
            # 0-0. 포트폴리오 계산 전에 최신 USD/KRW 환율 동기화
            #
            # 혼합통화 계좌의 평가액/비중 계산에서
            # 최신 환율을 사용할 수 있도록 가장 먼저 수집합니다.
            macro_data = {}
            macro_summary = ""

            try:
                macro_data = (
                    self.macro_service
                    .fetch_all_macro_data()
                )

                macro_summary = (
                    self.macro_service
                    .build_summary_for_gemini(
                        macro_data
                    )
                )

                usd_krw_data = (
                    macro_data
                    .get(
                        "macro_commodity",
                        {},
                    )
                    .get(
                        "usd_krw",
                        {},
                    )
                )

                if (
                    usd_krw_data.get("success")
                    is True
                ):
                    usd_krw_rate = float(
                        usd_krw_data.get(
                            "price",
                            0,
                        )
                        or 0
                    )

                    if usd_krw_rate > 0:
                        self.repo.save_exchange_rate(
                            rate_date=date.today(),
                            from_currency="USD",
                            to_currency="KRW",
                            rate=usd_krw_rate,
                        )

                        logger.info(
                            "포트폴리오 계산용 USD/KRW "
                            "환율 저장 완료: %.2f",
                            usd_krw_rate,
                        )

                logger.info(
                    "글로벌 10대 매크로 지표 및 "
                    "5일 트렌드 데이터 수집 완료"
                )

            except Exception as e:
                logger.warning(
                    "매크로 지표 사전 수집 중 오류 "
                    "(DB의 기존 환율로 계속 진행): %s",
                    e,
                )
            
            # 0. 리포트 생성 전 최신 시장 가격 데이터 수집 및 DB 동기화 (KRX 공식 Open API 또는 Mock)
            if update_prices:
                try:
                    logger.info("모닝 리포트 생성 전 최신 시장 가격 동기화 시작 (data_source: %s)...", self.config.data_source)
                    from data.price_updater import update_market_prices
                    # 매일 아침 직전 영업일 종가 수신을 위해 최근 5영업일 데이터 수집
                    update_res = update_market_prices(config=self.config, repo=self.repo, days=5)
                    logger.info("모닝 리포트 시장 가격 동기화 완료: %s", update_res)
                except Exception as e:
                    logger.warning("모닝 리포트 전 시장 가격 동기화 중 오류 (기존 DB 캐시 데이터로 계속 진행): %s", e)

            # 1. 전체 계좌 및 전체 등록 종목 데이터 집계 (통합 모드)
            accounts = self.repo.get_accounts()
            if len(accounts) > 1:
                account_name = f"전체 통합 포트폴리오 ({len(accounts)}개 계좌)"
            elif len(accounts) == 1:
                account_name = accounts[0].account_name
            else:
                account_name = "전체 등록 종목 통합"

            # 다중 계좌별 개별 요약, 계좌별 등록/보유 종목 세부현황 및 AI 추천 집계
            account_summaries = []
            account_groups = []
            account_recommendations = []
            for acc in accounts:
                try:
                    acc_pos_raw = self.portfolio_service.get_positions(account_id=acc.id)
                    acc_sum = self.portfolio_service.get_summary(acc_pos_raw, account_id=acc.id)
                    # 주식 평가액
                    acc_eval = getattr(
                        acc_sum,
                        "total_current_value",
                        0.0,
                    )

                    # 실제 매수원가
                    acc_cost = getattr(
                        acc_sum,
                        "total_invested",
                        0.0,
                    )

                    # 총손익: 평가손익 + 실현손익 + 배당금
                    acc_pl = getattr(
                        acc_sum,
                        "total_pnl",
                        getattr(
                            acc_sum,
                            "total_unrealized_pnl",
                            0.0,
                        ),
                    )

                    acc_pl_pct = (
                        getattr(
                            acc_sum,
                            "total_roi",
                            0.0,
                        )
                        * 100.0
                    )

                    # 실제 현금잔고
                    #
                    # 초기투자금
                    # + 추가입금
                    # - 출금
                    # - 매수대금
                    # + 매도대금
                    # + 배당금
                    acc_cash = (
                        self.portfolio_service
                        .get_cash_balance(
                            account_id=acc.id,
                            include_initial_capital=True,
                        )
                    )

                    # 계좌 총자산
                    #
                    # 주식 평가액 + 실제 현금잔고
                    acc_total_assets = (
                        float(
                            acc_eval
                            or 0
                        )
                        + float(
                            acc_cash
                            or 0
                        )
                    )

                    account_summaries.append({
                        "id": acc.id,
                        "name": acc.account_name,
                        "broker": acc.broker,
                        "currency": (
                            getattr(
                                acc,
                                "currency",
                                "KRW",
                            )
                            or "KRW"
                        ),
                        "total_eval": acc_eval,
                        "cash_balance": acc_cash,
                        "total_assets": acc_total_assets,                        
                        "total_pl": acc_pl,
                        "total_pl_pct": acc_pl_pct,
                    })
                    
                    # 해당 계좌의 목표 ETF 맵 구성
                    acc_targets = self.portfolio_service.get_target_etfs(account_id=acc.id)
                    acc_targets_map: Dict[str, ETFConfig] = {e.ticker: e for e in acc_targets}

                    # 해당 계좌의 보유 종목 (수량 > 0)
                    acc_positions = []
                    if isinstance(acc_pos_raw, dict):
                        for ticker, pos in acc_pos_raw.items():
                            if pos.quantity <= 0:
                                continue

                            account_currency = (
                                str(
                                    getattr(
                                        acc,
                                        "currency",
                                        "KRW",
                                    )
                                    or "KRW"
                                )
                                .strip()
                                .upper()
                            )

                            asset = (
                                self.repo
                                .get_etf_master(
                                    ticker
                                )
                            )

                            asset_currency = (
                                str(
                                    getattr(
                                        asset,
                                        "currency",
                                        None,
                                    )
                                    or getattr(
                                        pos,
                                        "currency",
                                        None,
                                    )
                                    or account_currency
                                )
                                .strip()
                                .upper()
                            )

                            # 종목 평가액은 native 통화이므로
                            # 계좌 전체 평가액과 비교하기 전에
                            # Account.currency로 환산합니다.
                            position_value_in_account_currency = (
                                self.portfolio_service
                                .convert_amount(
                                    value=float(
                                        pos.current_value
                                        or 0
                                    ),
                                    from_currency=(
                                        asset_currency
                                    ),
                                    to_currency=(
                                        account_currency
                                    ),
                                )
                            )

                            cur_w = (
                                position_value_in_account_currency
                                / acc_eval
                            ) if acc_eval > 0 else 0.0

                            tgt_w = acc_targets_map.get(
                                ticker,
                                ETFConfig(
                                    ticker,
                                    "",
                                    0.0,
                                ),
                            ).target_weight
                            
                            acc_positions.append({
                                "ticker": ticker,
                                "name":
                                    pos.name
                                    or ticker,
                                "currency":
                                    asset_currency,
                                "shares":
                                    pos.quantity,
                                "average_buy_price":
                                    pos.average_buy_price,
                                "total_buy_cost":
                                    pos.total_buy_cost,
                                "current_price":
                                    pos.current_price,
                                "eval_amount":
                                    pos.current_value,
                                "unrealized_pnl":
                                    pos.unrealized_pnl,
                                "realized_pnl":
                                    pos.realized_pnl,
                                "dividends":
                                    pos.total_dividends,
                                "total_pnl":
                                    pos.total_pnl,
                                "pl_pct":
                                    pos.unrealized_roi
                                    * 100.0,
                                "current_weight":
                                    cur_w,
                                "target_weight":
                                    tgt_w,
                            })
                            
                    # 해당 계좌 목표 ETF 중 미보유(수량=0) 종목도 편입 대기로 추가
                    acc_held_tickers = {p["ticker"] for p in acc_positions}
                    for ticker, etf in acc_targets_map.items():
                        if (
                            ticker
                            not in acc_held_tickers
                            and etf.target_weight > 0
                        ):
                            latest_p = (
                                self.repo
                                .get_latest_price(ticker)
                            )

                            cur_p = (
                                latest_p.close_price
                                if latest_p
                                else 0.0
                            )

                            asset = (
                                self.repo
                                .get_etf_master(ticker)
                            )

                            asset_currency = (
                                getattr(
                                    asset,
                                    "currency",
                                    None,
                                )
                                or getattr(
                                    acc,
                                    "currency",
                                    "KRW",
                                )
                                or "KRW"
                            )

                            acc_positions.append({
                                "ticker": ticker,
                                "name":
                                    etf.name
                                    or ticker,
                                "currency":
                                    asset_currency,
                                "shares": 0,
                                "current_price":
                                    cur_p,
                                "eval_amount": 0.0,
                                "pl_pct": 0.0,
                                "current_weight": 0.0,
                                "target_weight":
                                    etf.target_weight,
                            })
                            
                    account_groups.append({
                        "account_id": acc.id,
                        "account_name": acc.account_name,
                        "broker": acc.broker,
                        "currency": getattr(
                            acc,
                            "currency",
                            "KRW",
                        ) or "KRW",
                        "account_type": getattr(
                            acc,
                            "account_type",
                            "brokerage",
                        ) or "brokerage",
                        "market_scope": getattr(
                            acc,
                            "market_scope",
                            "KR",
                        ) or "KR",
                        "strategy_type": getattr(
                            acc,
                            "strategy_type",
                            "allocation",
                        ) or "allocation",
                        "initial_capital": float(
                            getattr(
                                acc,
                                "initial_capital",
                                0,
                            ) or 0
                        ),
                        "base_monthly": float(
                            getattr(
                                acc,
                                "base_monthly",
                                0,
                            ) or 0
                        ),
                        "max_additional_monthly": float(
                            getattr(
                                acc,
                                "max_additional_monthly",
                                0,
                            ) or 0
                        ),
                        "contribution_type": getattr(
                            acc,
                            "contribution_type",
                            "none",
                        ) or "none",
                        "contribution_amount": float(
                            getattr(
                                acc,
                                "contribution_amount",
                                0,
                            ) or 0
                        ),
                        "contribution_month": getattr(
                            acc,
                            "contribution_month",
                            None,
                        ),
                        "buy_cycle_type": getattr(
                            acc,
                            "buy_cycle_type",
                            "monthly",
                        ) or "monthly",
                        "buy_cycle_detail": getattr(
                            acc,
                            "buy_cycle_detail",
                            "25",
                        ) or "25",
                        "total_eval": acc_eval,
                        "total_assets": acc_total_assets,
                        "total_cost": acc_cost,
                        "total_pl": acc_pl,
                        "total_pl_pct": acc_pl_pct,
                        "cash_balance": acc_cash,
                        "positions": acc_positions,
                    })

                    # 해당 계좌의 투자 주기, D-Day 및 AI 매수 추천 집계
                    next_dt, d_day, desc = calculate_next_investment_date(
                        getattr(acc, "buy_cycle_type", "monthly"),
                        getattr(acc, "buy_cycle_detail", "25"),
                    )
                    rec_res = self.recommendation_service.calculate_recommendations(
                        account_id=acc.id, auto_save=False
                    )
                    rec_sum = rec_res.get("summary", {})
                    already_inv = rec_sum.get("already_invested_in_cycle", False)
                    c_desc = rec_sum.get("cycle_desc", desc)
                    tot_rec = rec_sum.get("total_recommended_buy", 0)
                    recs_raw = rec_res.get("recommendations", [])

                    acc_rec_items = []

                    for r in recs_raw:
                        account_currency = (
                            str(
                                getattr(
                                    acc,
                                    "currency",
                                    "KRW",
                                )
                                or "KRW"
                            )
                            .strip()
                            .upper()
                        )

                        available_amount = (
                            float(
                                r.recommended_buy
                                or 0
                            )
                            if not already_inv
                            else 0.0
                        )

                        # 추천 엔진의 available_amount는
                        # 계좌 기준통화 금액입니다.
                        #
                        # 실제 주문 수량 계산에는
                        # 종목 native 통화의 현재가를 사용해야 합니다.
                        position = (
                            acc_pos_raw.get(
                                r.ticker
                            )
                            if isinstance(
                                acc_pos_raw,
                                dict,
                            )
                            else None
                        )

                        asset = (
                            self.repo
                            .get_etf_master(
                                r.ticker
                            )
                        )

                        asset_currency = (
                            str(
                                getattr(
                                    asset,
                                    "currency",
                                    None,
                                )
                                or getattr(
                                    position,
                                    "currency",
                                    None,
                                )
                                or account_currency
                            )
                            .strip()
                            .upper()
                        )

                        native_current_price = (
                            float(
                                getattr(
                                    position,
                                    "current_price",
                                    0,
                                )
                                or 0
                            )
                            if position
                            else 0.0
                        )

                        # 미보유 목표 종목 등으로 position 가격이
                        # 없으면 DB의 최신 native 가격을 사용합니다.
                        if native_current_price <= 0:
                            latest_price = (
                                self.repo
                                .get_latest_price(
                                    r.ticker
                                )
                            )

                            if latest_price:
                                native_current_price = float(
                                    latest_price.close_price
                                    or 0
                                )

                        # 계좌통화 예산을 종목통화 예산으로
                        # 변환한 뒤 실제 매수 가능 주수를 계산합니다.
                        if (
                            available_amount > 0
                            and native_current_price > 0
                        ):
                            available_asset_budget = (
                                self.portfolio_service
                                .convert_amount(
                                    value=(
                                        available_amount
                                    ),
                                    from_currency=(
                                        account_currency
                                    ),
                                    to_currency=(
                                        asset_currency
                                    ),
                                )
                            )

                            available_shares = int(
                                available_asset_budget
                                // native_current_price
                            )

                        else:
                            available_asset_budget = 0.0
                            available_shares = 0

                        # 실제 주문금액은 우선 종목 native
                        # 통화로 계산합니다.
                        executable_asset_amount = (
                            available_shares
                            * native_current_price
                        )

                        # 계좌의 매수한도와 비교/표시할 수 있도록
                        # 실제 주문금액의 계좌통화 환산값도 보관합니다.
                        executable_account_amount = (
                            self.portfolio_service
                            .convert_amount(
                                value=(
                                    executable_asset_amount
                                ),
                                from_currency=(
                                    asset_currency
                                ),
                                to_currency=(
                                    account_currency
                                ),
                            )
                            if executable_asset_amount > 0
                            else 0.0
                        )

                        acc_rec_items.append({
                            "ticker":
                                r.ticker,

                            "name":
                                r.name,

                            "account_currency":
                                account_currency,

                            "asset_currency":
                                asset_currency,

                            "current_price":
                                native_current_price,

                            # 계좌 기준통화의 사용 가능 예산
                            "available_buy_budget":
                                available_amount,

                            # 종목통화로 환산한 사용 가능 예산
                            "available_asset_budget":
                                available_asset_budget,

                            "available_buy_shares":
                                available_shares,

                            # 종목 native 통화의 실제 주문금액
                            "executable_asset_amount":
                                executable_asset_amount,

                            # 계좌 기준통화로 환산한 실제 주문금액
                            "executable_account_amount":
                                executable_account_amount,

                            # 기존 HTML 코드와의 호환성을 위해
                            # 이 필드는 계좌 기준통화 금액으로 유지합니다.
                            "executable_buy_amount":
                                executable_account_amount,

                            "recommended_shares":
                                available_shares,

                            "recommended_amount":
                                executable_account_amount,

                            "reason":
                                r.reason,

                            "target_weight":
                                r.target_weight,

                            "current_weight":
                                r.current_weight,
                        })
                        
                    account_recommendations.append({
                        "account_id": acc.id,
                        "account_name": acc.account_name,
                        "broker": acc.broker,

                        # 계좌 평가액 / 매수 가능 예산 등에
                        # 사용할 계좌 기준 통화
                        "currency": (
                            getattr(
                                acc,
                                "currency",
                                "KRW",
                            )
                            or "KRW"
                        ),

                        "d_day": d_day,
                        "next_buy_date": (
                            next_dt.strftime("%Y-%m-%d")
                            if next_dt
                            else ""
                        ),
                        "cycle_desc": c_desc or desc,

                        # 이 값은 이제 단순히
                        # '현재 단계에서 추가 행동이 없는 상태'를
                        # 나타내는 호환용 값입니다.
                        "already_invested_this_month":
                            already_inv,

                        # 새 의미:
                        # 시스템 규칙상 현재 사용할 수 있는
                        # 최대 매수 예산.
                        "total_available_buy_budget": (
                            float(tot_rec or 0)
                            if not already_inv
                            else 0.0
                        ),

                        # 기존 HTML 호환용.
                        "total_recommended_amount": (
                            float(tot_rec or 0)
                            if not already_inv
                            else 0.0
                        ),

                        # Gemini가 이것을 자동 매수 명령으로
                        # 해석하지 않도록 의미를 명시합니다.
                        "budget_is_not_buy_order": True,

                        "items": acc_rec_items,
                    })
                except Exception as e:
                    logger.debug(f"계좌 [{acc.account_name}] 개별 요약, 종목 및 추천 집계 생략: {e}")

            # ---------------------------------------------------------
            # 전체 포트폴리오 포지션 및 요약
            #
            # 전체 자산 요약은 PortfolioService가 계좌별로 계산한 뒤
            # KRW 기준으로 통합합니다.
            #
            # 매수 추천은 계좌별 기준통화가 다를 수 있으므로
            # account_id=None으로 다시 계산하지 않습니다.
            # 위에서 이미 계산한 account_recommendations를 사용합니다.
            # ---------------------------------------------------------


            summary_raw = (
                self.portfolio_service
                .get_summary(
                    account_id=None
                )
            )

            # ---------------------------------------------------------
            # 대표 추천 데이터
            #
            # 계좌가 1개:
            #   해당 계좌의 추천을 기존 recommendations 형식으로
            #   그대로 전달하여 기존 HTML/Kakao/Gemini와 호환합니다.
            #
            # 계좌가 여러 개:
            #   서로 다른 기준통화의 예산을 절대 합산하지 않습니다.
            #   실제 추천 데이터는 account_recommendations에
            #   계좌별로 독립 저장되어 있습니다.
            # ---------------------------------------------------------

            if len(account_recommendations) == 1:

                single_rec = (
                    account_recommendations[0]
                )

                recommendations = {
                    "account_id":
                        single_rec.get(
                            "account_id"
                        ),

                    "account_name":
                        single_rec.get(
                            "account_name",
                            "",
                        ),

                    "currency":
                        single_rec.get(
                            "currency",
                            "KRW",
                        ),

                    "d_day":
                        single_rec.get(
                            "d_day"
                        ),

                    "next_buy_date":
                        single_rec.get(
                            "next_buy_date",
                            "",
                        ),

                    "cycle_desc":
                        single_rec.get(
                            "cycle_desc",
                            "",
                        ),

                    "already_invested_this_month":
                        single_rec.get(
                            "already_invested_this_month",
                            False,
                        ),

                    "total_available_buy_budget":
                        float(
                            single_rec.get(
                                "total_available_buy_budget",
                                0,
                            )
                            or 0
                        ),

                    # 기존 HTML 코드와의 호환성 유지
                    "total_recommended_amount":
                        float(
                            single_rec.get(
                                "total_available_buy_budget",
                                0,
                            )
                            or 0
                        ),

                    "budget_is_not_buy_order":
                        True,

                    "items":
                        single_rec.get(
                            "items",
                            [],
                        ),
                }

            elif len(account_recommendations) > 1:

                # -----------------------------------------------------
                # 다중 계좌에서는 KRW와 USD 등의 매수예산을
                # 하나의 숫자로 합산하지 않습니다.
                #
                # Gemini/HTML/Kakao는 account_recommendations의
                # 계좌별 예산과 통화를 사용해야 합니다.
                # -----------------------------------------------------

                recommendations = {
                    "account_id":
                        None,

                    "account_name":
                        "전체 계좌",

                    "currency":
                        None,

                    "d_day":
                        None,

                    "next_buy_date":
                        "",

                    "cycle_desc":
                        "계좌별 독립 매수",

                    "already_invested_this_month":
                        False,

                    # 중요:
                    # 서로 다른 통화의 예산을 합산하지 않습니다.
                    "total_available_buy_budget":
                        0.0,

                    "total_recommended_amount":
                        0.0,

                    "budget_is_not_buy_order":
                        True,

                    "multi_account":
                        True,

                    "budgets_are_account_specific":
                        True,

                    "items":
                        [],
                }

            else:

                # 계좌가 아직 없는 초기 상태
                recommendations = {
                    "account_id":
                        None,

                    "account_name":
                        "",

                    "currency":
                        "KRW",

                    "d_day":
                        None,

                    "next_buy_date":
                        "",

                    "cycle_desc":
                        "수시 매수",

                    "already_invested_this_month":
                        False,

                    "total_available_buy_budget":
                        0.0,

                    "total_recommended_amount":
                        0.0,

                    "budget_is_not_buy_order":
                        True,

                    "items":
                        [],
                }
                

            # ---------------------------------------------------------
            # 전체 포트폴리오 요약
            #
            # 모든 계좌의
            # 주식 평가액 + 실제 예수금을
            # KRW로 환산하여 전체 총자산을 계산합니다.
            # ---------------------------------------------------------

            overall_portfolio_summary = (
                self.portfolio_service.get_summary(
                    account_id=None
                )
            )
            summary = self._build_overall_portfolio_summary(
                overall_portfolio_summary
            )

            # 1-1. 전체 등록 종목 맵 구성
            #
            # 전체 포트폴리오의 종목 표시 데이터는 더 이상
            # account_id=None으로 합쳐진 positions_raw를 사용하지 않습니다.
            #
            # 계좌별로 이미 계산된 account_groups의 positions를 기반으로
            # 전체 표시용 목록을 만듭니다.
            #
            # 이유:
            # - 같은 ticker가 여러 계좌에 존재할 수 있음
            # - 계좌마다 기준통화가 다를 수 있음
            # - 종목 자체의 거래통화도 다를 수 있음
            # - 종목 비중은 계좌 기준통화로 환산된 계좌별 비중을 사용해야 함

            target_etfs = (
                self.portfolio_service
                .get_target_etfs(
                    account_id=None
                )
            )

            registered_etfs_map: Dict[
                str,
                ETFConfig,
            ] = {}

            for e in target_etfs:
                registered_etfs_map[
                    e.ticker
                ] = e

            for e in self.config.etfs:
                if (
                    e.ticker
                    not in registered_etfs_map
                ):
                    registered_etfs_map[
                        e.ticker
                    ] = e

            positions = []

            # 정적 GitHub Pages에는 인증정보 없이 표시 가능한 가격/매매
            # 데이터만 최대 260개 시점으로 제한하여 포함합니다.
            self._attach_report_chart_data(account_groups)

            # ---------------------------------------------------------
            # 계좌별 포지션을 그대로 유지하면서
            # 전체 리포트 전달용 positions를 구성합니다.
            #
            # current_weight는 account_groups 생성 단계에서 이미
            # 종목 평가액을 Account.currency로 환산하여 계산했습니다.
            # 따라서 여기서 native 평가액을 전체 KRW 평가액으로
            # 다시 나누지 않습니다.
            # ---------------------------------------------------------

            for account_group in account_groups:
                group_account_id = (
                    account_group.get(
                        "account_id"
                    )
                )

                group_account_name = (
                    account_group.get(
                        "account_name",
                        "",
                    )
                )

                group_account_currency = (
                    str(
                        account_group.get(
                            "currency",
                            "KRW",
                        )
                        or "KRW"
                    )
                    .strip()
                    .upper()
                )

                for position in (
                    account_group.get(
                        "positions",
                        [],
                    )
                    or []
                ):
                    position_data = dict(
                        position
                    )

                    # 어느 계좌의 종목인지 명시적으로 유지합니다.
                    position_data[
                        "account_id"
                    ] = group_account_id

                    position_data[
                        "account_name"
                    ] = group_account_name

                    position_data[
                        "account_currency"
                    ] = group_account_currency

                    # currency는 개별 종목의 native 거래통화입니다.
                    position_data[
                        "currency"
                    ] = (
                        str(
                            position_data.get(
                                "currency",
                                group_account_currency,
                            )
                            or group_account_currency
                        )
                        .strip()
                        .upper()
                    )

                    positions.append(
                        position_data
                    )

            # ---------------------------------------------------------
            # 계좌가 아직 없는 초기 상태에서 config에 등록된 ETF가
            # 있을 경우에만 fallback 목록을 만듭니다.
            #
            # 실제 계좌가 하나라도 있으면 account_groups가
            # source of truth입니다.
            # ---------------------------------------------------------

            if not account_groups:
                for ticker, etf in (
                    registered_etfs_map.items()
                ):
                    if (
                        etf.target_weight
                        <= 0
                    ):
                        continue

                    latest_p = (
                        self.repo
                        .get_latest_price(
                            ticker
                        )
                    )

                    cur_p = (
                        float(
                            latest_p.close_price
                            or 0
                        )
                        if latest_p
                        else 0.0
                    )

                    asset = (
                        self.repo
                        .get_etf_master(
                            ticker
                        )
                    )

                    asset_currency = (
                        str(
                            getattr(
                                asset,
                                "currency",
                                None,
                            )
                            or "KRW"
                        )
                        .strip()
                        .upper()
                    )

                    positions.append({
                        "account_id":
                            None,

                        "account_name":
                            "",

                        "account_currency":
                            "KRW",

                        "ticker":
                            ticker,

                        "name":
                            etf.name
                            or ticker,

                        "currency":
                            asset_currency,

                        "shares":
                            0,

                        "current_price":
                            cur_p,

                        "eval_amount":
                            0.0,

                        "pl_pct":
                            0.0,

                        "current_weight":
                            0.0,

                        "target_weight":
                            etf.target_weight,
                    })                    

            # 2. 맞춤 뉴스 수집 (전체 등록 종목 대상)
            news_items = []
            if self.config.morning_report.include_news:
                all_registered_objs = list(registered_etfs_map.values())
                if not all_registered_objs:
                    all_registered_objs = [ETFConfig(ticker=p["ticker"], name=p["name"], target_weight=p["target_weight"]) for p in positions]
                feed = self.news_service.get_news_feed(
                    mode=getattr(self.config, "news_filter_mode", "all"),
                    etfs=all_registered_objs,
                    watchlist=self.config.watchlist,
                )
                for item in feed[:8]:
                    news_items.append({
                        "title": item.get("title", ""),
                        "media": item.get("press", "금융뉴스"),
                        "date": item.get("datetime", ""),
                        "link": item.get("link", "#"),
                        "tag": item.get("tag", "증시"),
                    })

            # 3. 시장 지수 요약 (대표 지수 샘플)
            market_indices = {}
            if self.config.morning_report.include_market_indices:
                # KOSPI 200 등 시세 조회
                p_hist = self.repo.get_prices("069500", limit=2)
                if p_hist:
                    latest = p_hist[-1]
                    chg_pct = 0.0
                    if len(p_hist) >= 2 and p_hist[-2].close_price > 0:
                        prev_close = p_hist[-2].close_price
                        latest_close = float(
                            latest.close_price or 0
                        )
                        
                        previous_close = float(
                            prev_close or 0
                        )
                        
                        if previous_close > 0:
                            chg_pct = (
                                (
                                    latest_close
                                    - previous_close
                                )
                                / previous_close
                            ) * 100.0
                        else:
                            chg_pct = 0.0
                        
                    elif latest.open_price and latest.open_price > 0:
                        chg_pct = ((latest.close_price - latest.open_price) / latest.open_price) * 100.0
                    market_indices["KODEX 200"] = {
                        "price": f"{latest.close_price:,.0f}원",
                        "change_pct": round(chg_pct, 2),
                    }
                
            # 3-2. 사용자 투자 성향 및 투자 원칙 조회
            investment_profile_data = {}

            try:
                investment_profile = (
                    self.repo.get_investment_profile()
                )

                if investment_profile is not None:
                    investment_profile_data = {
                        "risk_profile":
                            investment_profile.risk_profile
                            or "balanced",

                        "investment_horizon_years":
                            investment_profile
                            .investment_horizon_years,

                        "target_return":
                            (
                                float(
                                    investment_profile
                                    .target_return
                                )
                                if investment_profile
                                .target_return
                                is not None
                                else None
                            ),

                        "max_drawdown":
                            (
                                float(
                                    investment_profile
                                    .max_drawdown
                                )
                                if investment_profile
                                .max_drawdown
                                is not None
                                else None
                            ),

                        "preferred_markets":
                            investment_profile
                            .preferred_markets
                            or [],

                        "excluded_assets":
                            investment_profile
                            .excluded_assets
                            or [],

                        "ai_advice_enabled":
                            bool(
                                investment_profile
                                .ai_advice_enabled
                            ),

                        "ai_advice_style":
                            investment_profile
                            .ai_advice_style
                            or "balanced",

                        "memo":
                            investment_profile.memo
                            or "",

                        "investment_preference_text":
                            investment_profile
                            .investment_preference_text
                            or "",
                    }

                    logger.info(
                        "사용자 투자 성향 및 투자 원칙을 "
                        "모닝 리포트에 반영합니다."
                    )

            except Exception as e:
                logger.warning(
                    "사용자 투자 성향 조회 중 오류 "
                    "(기본 설정으로 계속 진행): %s",
                    e,
                )

            # AI에 전달할 최근 거래와 관심종목은 조회 가능한 데이터만 사용합니다.
            recent_transactions = []
            watchlist = []

            try:
                for transaction in self.repo.get_transactions()[:20]:
                    recent_transactions.append({
                        "date": str(getattr(transaction, "transaction_date", "")),
                        "account_id": getattr(transaction, "account_id", None),
                        "ticker": getattr(transaction, "ticker", ""),
                        "type": getattr(transaction, "transaction_type", ""),
                        "quantity": float(getattr(transaction, "quantity", 0) or 0),
                        "price": float(getattr(transaction, "price", 0) or 0),
                        "fee": float(getattr(transaction, "fee", 0) or 0),
                        "tax": float(getattr(transaction, "tax", 0) or 0),
                    })
            except Exception as exc:
                logger.warning("AI 입력용 최근 거래 조회를 생략합니다: %s", type(exc).__name__)

            try:
                watchlist = self.repo.get_watchlist() or []
            except Exception as exc:
                logger.warning("AI 입력용 관심종목 조회를 생략합니다: %s", type(exc).__name__)

            # 4. Google Gemini AI 투자 분석 생성 (실패해도 보고서는 계속 생성)
            gemini_analysis = {}

            ai_advice_enabled = bool(
                investment_profile_data.get(
                    "ai_advice_enabled",
                    True,
                )
            )

            gemini_enabled = getattr(
                self.config.morning_report,
                "gemini_enabled",
                True,
            )

            ai_context = {
                                "account_name":
                                    account_name,

                                "summary":
                                    summary,

                                "recommendations":
                                    recommendations,

                                "positions":
                                    positions,

                                "news":
                                    news_items,

                                "market_indices":
                                    market_indices,

                                "macro_summary":
                                    macro_summary,

                                "macro_indicators":
                                    macro_data,

                                "investment_profile":
                                    investment_profile_data,

                                "account_groups":
                                    account_groups,

                                "account_recommendations":
                                    account_recommendations,
                                "recent_transactions": recent_transactions,
                                "watchlist": watchlist,
                            }

            gemini_analysis = self._generate_ai_analysis(
                ai_context,
                enabled=(gemini_enabled and ai_advice_enabled),
            )

            if not ai_advice_enabled:
                logger.info(
                    "사용자 설정에서 AI 투자 가이드가 "
                    "비활성화되어 Gemini 호출을 건너뜁니다."
                )
                
            report_data = {
                "account_name": account_name,
                "summary": summary,
                "account_summaries": account_summaries,
                "account_groups": account_groups,
                "recommendations": recommendations,
                "account_recommendations": account_recommendations,
                "positions": positions,
                "news": news_items,
                "market_indices": market_indices,
                "macro_indicators": macro_data,
                "investment_profile": investment_profile_data,
                "gemini_analysis": gemini_analysis,
                "portfolio_management_url": get_web_app_url(),
            }

            # 5. 모바일 반응형 HTML 생성
            html_file = self.html_generator.generate_html(report_data)
            logger.info(f"모닝 리포트 HTML 생성 완료: {html_file}")

            if self.repo.user_id:
                self.repo.upsert_morning_report(
                    datetime.date.today(),
                    html_file.read_text(encoding="utf-8"),
                )
                logger.info("사용자별 모닝 리포트 DB 저장 완료")
            else:
                logger.warning("user_id가 없어 로컬 리포트를 DB에 저장하지 않았습니다.")

            report_web_url = get_report_url()

            summary_text = self._build_kakao_summary_text(
                account_name=account_name,
                summary=summary,
                recommendations=recommendations,
                news_items=news_items,
                report_web_url=report_web_url,
                gemini_analysis=gemini_analysis,
                macro_data=macro_data,
                positions=positions,
                account_summaries=account_summaries,
                account_groups=account_groups,
                account_recommendations=account_recommendations,
            )

            # Multi-user mode sends directly with the authenticated user's
            # credential. Do not write portfolio/Kakao payloads to a shared file.

            # 6. 카카오톡 메시지 전송
            kakao_status = "카카오톡 미발송"
            if send_kakao:
                should_send = force_kakao or bool(self.config.morning_report.enabled)
                if should_send:
                    if not self.kakao_service.is_configured():
                        return False, "카카오톡 토큰이 설정되지 않았습니다. [환경 설정]에서 토큰을 입력해주세요.", html_file

                    ok, msg = self.kakao_service.send_morning_report(summary_text, report_web_url)
                    if not ok:
                        return False, f"리포트 HTML은 생성되었으나 카카오톡 전송에 실패했습니다: {msg}", html_file
                    if self.repo.user_id:
                        self.repo.mark_morning_report_kakao_sent(datetime.date.today())
                    kakao_status = "카카오톡 발송 성공!"
                else:
                    kakao_status = "카카오톡 미발송 (설정에서 모닝 리포트 발송 기능이 꺼져 있음)"

            return True, f"모닝 리포트가 성공적으로 준비되었습니다. ({kakao_status})", html_file

        except Exception as e:
            logger.exception("모닝 리포트 생성 및 발송 실패")
            return False, f"오류 발생: {str(e)}", None

    def _build_kakao_summary_text(
        self,
        account_name: str,
        summary: Dict[str, Any],
        recommendations: Dict[str, Any],
        news_items: list,
        report_web_url: str = "",
        gemini_analysis: Optional[Dict[str, Any]] = None,
        macro_data: Optional[Dict[str, Any]] = None,
        positions: Optional[List[Dict[str, Any]]] = None,
        account_summaries: Optional[List[Dict[str, Any]]] = None,
        account_groups: Optional[List[Dict[str, Any]]] = None,
        account_recommendations: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """카카오톡 채팅방에 보낼 전체 등록 종목 및 포트폴리오 요약 텍스트 생성"""
        now = datetime.datetime.now()
        date_str = now.strftime("%Y.%m.%d")
        weekday_kr = ["월", "화", "수", "목", "금", "토", "일"][now.weekday()]

        total_assets = summary.get(
            "total_assets",
            summary.get("total_eval", 0),
        )
        stock_eval = summary.get("stock_eval", 0)
        cash_balance = summary.get("cash_balance", 0)
        total_cost = summary.get("total_cost", 0)
        total_pl = summary.get("total_pl", 0)
        total_pl_pct = summary.get("total_pl_pct", 0.0)
        sign = "+" if total_pl > 0 else ""

        d_day = recommendations.get("d_day", None)

        available_budget = float(
            recommendations.get(
                "total_available_buy_budget",
                0,
            ) or 0
        )

        # 단일 계좌일 때 매수 가능 예산은
        # 해당 계좌의 기준 통화로 표시합니다.
        single_account_currency = "KRW"

        if account_groups and len(account_groups) == 1:
            single_account_currency = (
                account_groups[0].get(
                    "currency",
                    "KRW",
                )
                or "KRW"
            )

        formatted_available_budget = (
            self._format_money(
                available_budget,
                single_account_currency,
            )
        )        
        
        if d_day == 0:
            guide_text = (
                f"오늘 정기 매수 검토 기준일 "
                f"(매수 가능 예산 최대 "
                f"{formatted_available_budget})"
            )

        elif d_day is not None:
            guide_text = (
                f"정기 매수 검토 기준일까지 "
                f"D-{d_day} "
                f"({recommendations.get('next_buy_date', '')})"
            )

        else:
            guide_text = (
                f"매수 가능 예산 최대 "
                f"{formatted_available_budget}"
            )
            

        already_invested = recommendations.get(
            "already_invested_this_month",
            False,
        )

        lines = [
            f"🌅 [포트폴리오 모닝 리포트] {date_str} ({weekday_kr})",
            f"• 계좌: {account_name}",
            f"• 총자산: {total_assets:,.0f}원 ({sign}{total_pl_pct:.2f}%)",
            f"• 주식평가액: {stock_eval:,.0f}원",
            f"• 예수금: {cash_balance:,.0f}원",
            f"• 주식 매수원가: {total_cost:,.0f}원",
            f"• 총손익: {sign}{total_pl:,.0f}원",
        ]

        # 다중 계좌 등록 시 계좌별 요약 한 줄 표시
        if account_summaries and len(account_summaries) > 1:
            acc_strs = []

            for a in account_summaries:
                s_sign = (
                    "+"
                    if a["total_pl"] > 0
                    else ""
                )

                currency = (
                    a.get("currency", "KRW")
                    or "KRW"
                )

                formatted_total_assets = (
                    self._format_money(
                        a.get(
                            "total_assets",
                            a.get(
                                "total_eval",
                                0,
                            ),
                        ),
                        currency,
                    )
                )

                acc_strs.append(
                    f"{a['name']} "
                    f"{formatted_total_assets}"
                    f"({s_sign}"
                    f"{a['total_pl_pct']:.1f}%)"
                )

            lines.append(
                f"• 계좌별: "
                f"{' | '.join(acc_strs)}"
            )
            
        # 계좌별 투자 가이드 및 매수 가능 예산
        if (
            account_recommendations
            and len(account_recommendations) > 1
        ):
            g_lines = []

            for ar in account_recommendations:
                ar_name = ar.get(
                    "account_name",
                    "",
                )

                ar_already = ar.get(
                    "already_invested_this_month",
                    False,
                )

                ar_dday = ar.get("d_day")

                ar_next = ar.get(
                    "next_buy_date",
                    "",
                )

                ar_currency = (
                    ar.get(
                        "currency",
                        "KRW",
                    )
                    or "KRW"
                )

                ar_budget = float(
                    ar.get(
                        "total_available_buy_budget",
                        0,
                    )
                    or 0
                )

                formatted_ar_budget = (
                    self._format_money(
                        ar_budget,
                        ar_currency,
                    )
                )

                if ar_already:
                    g_lines.append(
                        f"{ar_name}: 완료"
                    )

                elif ar_dday == 0:
                    g_lines.append(
                        f"{ar_name}: 🚨D-Day "
                        f"(최대 {formatted_ar_budget})"
                    )

                elif ar_dday is not None:
                    g_lines.append(
                        f"{ar_name}: "
                        f"D-{ar_dday}({ar_next}) "
                        f"(최대 {formatted_ar_budget})"
                    )

                else:
                    g_lines.append(
                        f"{ar_name}: 수시 "
                        f"(최대 {formatted_ar_budget})"
                    )

            lines.append(
                f"• 매수주기: "
                f"{' | '.join(g_lines)}"
            )

        else:
            lines.append(
                f"• 투자 가이드: {guide_text}"
            )
            
        # 10대 글로벌 매크로 및 트렌드 요약 (미국 3대, 국내 2대, 환율/유가/금리, PCE/고용)
        if macro_data:
            try:
                macro_lines = self.macro_service.build_kakao_macro_lines(macro_data)
                if macro_lines:
                    lines.append("")
                    lines.extend(macro_lines)
            except Exception as e:
                logger.debug(f"카카오 매크로 라인 생성 생략: {e}")

        # Gemini AI 행동 판단 + 한 줄 요약
        if (
            gemini_analysis
            and gemini_analysis.get("success")
        ):
            action = str(
                gemini_analysis.get(
                    "action",
                    "HOLD",
                )
                or "HOLD"
            ).strip().upper()
        
            action_label = str(
                gemini_analysis.get(
                    "action_label",
                    "",
                )
                or ""
            ).strip()
        
            action_info = {
                "BUY": (
                    "매수",
                    "현재 매수 가능 범위 안에서 매수를 검토하는 판단",
                ),
                "PARTIAL": (
                    "일부 매수",
                    "현재 매수 가능 범위의 일부만 사용하는 판단",
                ),
                "WAIT": (
                    "대기",
                    "매수 가능 예산을 지금 사용하지 않고 기다리는 판단",
                ),
                "HOLD": (
                    "기존 계획 유지",
                    "별도 행동 없이 현재 투자 계획을 유지하는 판단",
                ),
            }
        
            default_label, action_desc = (
                action_info.get(
                    action,
                    action_info["HOLD"],
                )
            )
        
            if not action_label:
                action_label = default_label
        
            lines.append(
                f"\n🤖 AI 행동 판단: {action_label}"
            )
            lines.append(
                f"• {action_desc}"
            )
        
            ai_take = str(
                gemini_analysis.get(
                    "one_line_summary",
                    "",
                )
                or ""
            ).strip()
        
            stance_badge = gemini_analysis.get(
                "stance_badge"
            )
        
            if ai_take:
                if stance_badge:
                    lines.append(
                        f"• AI 요약 [{stance_badge}]: "
                        f"{ai_take}"
                    )
                else:
                    lines.append(
                        f"• AI 요약: {ai_take}"
                    )

        elif gemini_analysis:
            fallback_text = str(
                gemini_analysis.get(
                    "one_line_summary",
                    "AI 분석을 일시적으로 사용할 수 없습니다.",
                )
                or "AI 분석을 일시적으로 사용할 수 없습니다."
            ).strip()
            lines.append(f"\n🤖 AI 투자분석: {fallback_text}")

        # 등록 및 보유 종목 세부 현황
        # 개별 종목 가격은 계좌 통화가 아니라
        # asset_master에 저장된 종목 통화를 기준으로 표시합니다.
        if account_groups and len(account_groups) > 1:
            total_stocks = sum(
                len(
                    ag.get(
                        "positions",
                        [],
                    )
                )
                for ag in account_groups
            )

            lines.append(
                f"\n📋 계좌별 등록·보유 종목 현황 "
                f"({total_stocks}개):"
            )

            for ag in account_groups:
                ag_name = ag.get(
                    "account_name",
                    "",
                )

                ag_pos = ag.get(
                    "positions",
                    [],
                )

                if not ag_pos:
                    continue

                ag_pct = float(
                    ag.get(
                        "total_pl_pct",
                        0.0,
                    )
                    or 0.0
                )

                ag_sign = (
                    "+"
                    if ag_pct > 0
                    else ""
                )

                lines.append(
                    f"\n[{ag_name}] "
                    f"({ag_sign}{ag_pct:.1f}%)"
                )

                for p in ag_pos:
                    p_name = p.get(
                        "name",
                        "",
                    )

                    p_price = float(
                        p.get(
                            "current_price",
                            0,
                        )
                        or 0
                    )

                    # 중요:
                    # 종목 가격은 Account.currency가 아니라
                    # AssetMaster.currency를 사용합니다.
                    p_currency = (
                        p.get(
                            "currency",
                            "KRW",
                        )
                        or "KRW"
                    )

                    formatted_price = (
                        self._format_money(
                            p_price,
                            p_currency,
                        )
                    )

                    p_pl = float(
                        p.get(
                            "pl_pct",
                            0.0,
                        )
                        or 0.0
                    )

                    p_cur_w = (
                        float(
                            p.get(
                                "current_weight",
                                0.0,
                            )
                            or 0.0
                        )
                        * 100
                    )

                    p_tgt_w = (
                        float(
                            p.get(
                                "target_weight",
                                0.0,
                            )
                            or 0.0
                        )
                        * 100
                    )

                    p_shares = float(
                        p.get(
                            "shares",
                            0,
                        )
                        or 0
                    )

                    p_sign = (
                        "+"
                        if p_pl > 0
                        else ""
                    )

                    if p_shares > 0:
                        line = (
                            f"• {p_name}: "
                            f"{formatted_price} "
                            f"({p_sign}{p_pl:.1f}% | "
                            f"비중 {p_cur_w:.1f}%)"
                        )

                    else:
                        line = (
                            f"• {p_name}: "
                            f"{formatted_price} "
                            f"(미보유 | "
                            f"목표 {p_tgt_w:.1f}%)"
                        )

                    if (
                        sum(
                            len(l)
                            for l in lines
                        )
                        + len(line)
                        > 900
                    ):
                        lines.append(
                            "• ... "
                            "(상세 종목은 모바일 "
                            "리포트에서 확인)"
                        )
                        break

                    lines.append(line)

        elif positions:
            lines.append(
                f"\n📋 전체 등록 종목 현황 "
                f"({len(positions)}개):"
            )

            for p in positions:
                p_name = p.get(
                    "name",
                    "",
                )

                p_price = float(
                    p.get(
                        "current_price",
                        0,
                    )
                    or 0
                )

                p_currency = (
                    p.get(
                        "currency",
                        "KRW",
                    )
                    or "KRW"
                )

                formatted_price = (
                    self._format_money(
                        p_price,
                        p_currency,
                    )
                )

                p_pl = float(
                    p.get(
                        "pl_pct",
                        0.0,
                    )
                    or 0.0
                )

                p_cur_w = (
                    float(
                        p.get(
                            "current_weight",
                            0.0,
                        )
                        or 0.0
                    )
                    * 100
                )

                p_tgt_w = (
                    float(
                        p.get(
                            "target_weight",
                            0.0,
                        )
                        or 0.0
                    )
                    * 100
                )

                p_shares = float(
                    p.get(
                        "shares",
                        0,
                    )
                    or 0
                )

                p_sign = (
                    "+"
                    if p_pl > 0
                    else ""
                )

                if p_shares > 0:
                    line = (
                        f"• {p_name}: "
                        f"{formatted_price} "
                        f"({p_sign}{p_pl:.1f}% | "
                        f"비중 {p_cur_w:.1f}%)"
                    )

                else:
                    line = (
                        f"• {p_name}: "
                        f"{formatted_price} "
                        f"(미보유 | "
                        f"목표 {p_tgt_w:.1f}%)"
                    )

                if (
                    sum(
                        len(l)
                        for l in lines
                    )
                    + len(line)
                    > 900
                ):
                    lines.append(
                        "• ... "
                        "(상세 종목은 모바일 "
                        "리포트에서 확인)"
                    )
                    break

                lines.append(line)
                
        # 매수 가능 범위
        # 정량 엔진은 매수 여부를 결정하지 않고,
        # 현재 계좌 규칙상 사용할 수 있는 최대 범위만 표시합니다.
        if account_recommendations and len(account_recommendations) > 1:
            capacity_blocks = []

            for ar in account_recommendations:
                ar_name = ar.get(
                    "account_name",
                    "",
                )

                ar_budget = float(
                    ar.get(
                        "total_available_buy_budget",
                        0,
                    ) or 0
                )

                ar_items = [
                    it
                    for it in ar.get("items", [])
                    if (
                        float(
                            it.get(
                                "available_buy_budget",
                                0,
                            ) or 0
                        ) > 0
                    )
                ]

                if ar_budget <= 0 and not ar_items:
                    continue

                ar_currency = (
                    ar.get(
                        "currency",
                        "KRW",
                    )
                    or "KRW"
                )

                capacity_blocks.append(
                    f"[{ar_name}] 최대 "
                    f"{self._format_money(ar_budget, ar_currency)}"
                )

                for it in ar_items:
                    shares = int(
                        it.get(
                            "available_buy_shares",
                            0,
                        ) or 0
                    )

                    executable_amount = float(
                        it.get(
                            "executable_account_amount",
                            it.get(
                                "executable_buy_amount",
                                0,
                            ),
                        )
                        or 0
                    )

                    if shares > 0:
                        capacity_blocks.append(
                            f"• {it.get('name')}: "
                            f"최대 {shares:,}주 "
                            f"({self._format_money(executable_amount, ar_currency)})"
                        )
                        

            if capacity_blocks:
                lines.append(
                    "\n📐 계좌별 매수 가능 범위:"
                )
                lines.extend(
                    capacity_blocks
                )

        else:
            available_budget = float(
                recommendations.get(
                    "total_available_buy_budget",
                    0,
                ) or 0
            )

            items = recommendations.get(
                "items",
                [],
            )

            capacity_items = [
                it
                for it in items
                if (
                    float(
                        it.get(
                            "available_buy_budget",
                            0,
                        ) or 0
                    ) > 0
                )
            ]

            if (
                available_budget > 0
                or capacity_items
            ):
                lines.append(
                    f"\n📐 매수 가능 범위: "
                    f"최대 "
                    f"{self._format_money(available_budget, single_account_currency)}"
                )

                for it in capacity_items:
                    shares = int(
                        it.get(
                            "available_buy_shares",
                            0,
                        ) or 0
                    )

                    executable_amount = float(
                        it.get(
                            "executable_account_amount",
                            it.get(
                                "executable_buy_amount",
                                0,
                            ),
                        )
                        or 0
                    )

                    if shares > 0:
                        lines.append(
                            f"• {it.get('name')}: "
                            f"최대 {shares:,}주 "
                            f"({self._format_money(executable_amount, single_account_currency)})"
                        )
                        
                lines.append(
                    "• 위 금액은 자동 매수 지시가 아닌 "
                    "현재 규칙상 사용 가능한 최대 범위"
                )
                
        # 뉴스 1건 (AI 시황이 없을 때 주요 시황으로 표출)
        if (not gemini_analysis or not gemini_analysis.get("success")) and news_items:
            first_news = news_items[0].get("title", "")
            if len(first_news) > 30:
                first_news = first_news[:28] + "..."
            lines.append(f"\n• 주요 시황: {first_news}")

        if report_web_url and report_web_url.startswith("http") and "localhost" not in report_web_url:
            lines.append(f"\n📊 모바일 상세 리포트 열기:\n👉 {report_web_url}")
        else:
            lines.append("\n아래 [모바일 상세 리포트 열기]를 눌러 전체 리포트를 확인하세요!")
        return "\n".join(lines)

    def send_cached_kakao(self) -> Tuple[bool, str]:
        """GitHub Actions 등에서 Pages 배포 완료 후 캐시된 리포트 데이터를 카카오톡으로 발송합니다."""
        payload_cache = get_project_root() / "exports" / ".kakao_payload.json"
        if not payload_cache.exists():
            return False, "캐시된 카카오톡 발송 데이터(.kakao_payload.json)를 찾을 수 없습니다."
        try:
            import json
            data = json.loads(payload_cache.read_text(encoding="utf-8"))
            summary_text = data.get("summary_text", "")
            report_web_url = validate_public_url(
                data.get("report_web_url"),
                get_report_url(),
            )
            if not self.kakao_service.is_configured():
                return False, "카카오톡 토큰이 설정되지 않았습니다."
            return self.kakao_service.send_morning_report(summary_text, report_web_url)
        except Exception as e:
            return False, f"카카오 발송 실패: {e}"


def run_daily_report_cli():
    """CLI 환경에서 모닝 리포트를 생성하고 발송합니다."""
    if sys.platform == "win32":
        try:
            if sys.stdout and hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            if sys.stderr and hasattr(sys.stderr, "reconfigure"):
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    init_db()
    service = DailyReportService()

    if "--send-kakao-only" in sys.argv:
        print("=== GitHub Pages 배포 완료 후 카카오톡 알림 발송 시작 ===")
        success, msg = service.send_cached_kakao()
        if success:
            print(f"[성공] {msg}")
        else:
            print(f"[실패] {msg}")
            sys.exit(1)
        return

    generate_only = "--generate-only" in sys.argv
    print(f"=== 모닝 포트폴리오 리포트 생성 시작 (발송 포함: {not generate_only}) ===")
    success, msg, file_path = service.generate_and_send(send_kakao=not generate_only, force_kakao=not generate_only)
    if success:
        print(f"[성공] {msg}")
        print(f"[파일] {file_path}")
    else:
        print(f"[실패] {msg}")
        sys.exit(1)


if __name__ == "__main__":
    run_daily_report_cli()
