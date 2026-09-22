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
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from core.config import AppConfig, MorningReportConfig, ETFConfig, load_config
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
        self.repo = repo or Repository()
        self.portfolio_service = PortfolioService(self.repo, self.config)
        self.recommendation_service = RecommendationService(self.repo, self.config, portfolio_service=self.portfolio_service)
        self.news_service = NewsService()
        self.html_generator = ReportHtmlGenerator(self.config.morning_report)
        self.kakao_service = KakaoService(self.config)
        self.gemini_service = GeminiService(self.config)
        self.macro_service = MacroIndicatorService()

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
                    acc_eval = getattr(acc_sum, "total_current_value", 0.0)
                    acc_cost = getattr(acc_sum, "total_invested", 0.0)
                    acc_pl = getattr(acc_sum, "total_pnl", getattr(acc_sum, "total_unrealized_pnl", 0.0))
                    acc_pl_pct = getattr(acc_sum, "total_roi", 0.0) * 100.0
                    acc_cash = getattr(acc_sum, "remaining_cash", 0.0)

                    account_summaries.append({
                        "id": acc.id,
                        "name": acc.account_name,
                        "broker": acc.broker,
                        "total_eval": acc_eval,
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
                            cur_w = (pos.current_value / acc_eval) if acc_eval > 0 else 0.0
                            tgt_w = acc_targets_map.get(ticker, ETFConfig(ticker, "", 0.0)).target_weight
                            acc_positions.append({
                                "ticker": ticker,
                                "name": pos.name or ticker,
                                "shares": pos.quantity,
                                "current_price": pos.current_price,
                                "eval_amount": pos.current_value,
                                "pl_pct": pos.unrealized_roi * 100.0,
                                "current_weight": cur_w,
                                "target_weight": tgt_w,
                            })

                    # 해당 계좌 목표 ETF 중 미보유(수량=0) 종목도 편입 대기로 추가
                    acc_held_tickers = {p["ticker"] for p in acc_positions}
                    for ticker, etf in acc_targets_map.items():
                        if ticker not in acc_held_tickers and etf.target_weight > 0:
                            latest_p = self.repo.get_latest_price(ticker)
                            cur_p = latest_p.close_price if latest_p else 0.0
                            acc_positions.append({
                                "ticker": ticker,
                                "name": etf.name or ticker,
                                "shares": 0,
                                "current_price": cur_p,
                                "eval_amount": 0.0,
                                "pl_pct": 0.0,
                                "current_weight": 0.0,
                                "target_weight": etf.target_weight,
                            })

                    account_groups.append({
                        "account_id": acc.id,
                        "account_name": acc.account_name,
                        "broker": acc.broker,
                        "total_eval": acc_eval,
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
                        shares = int(r.recommended_buy // r.current_price) if (r.current_price > 0 and not already_inv) else 0
                        amt = r.recommended_buy if not already_inv else 0
                        acc_rec_items.append({
                            "ticker": r.ticker,
                            "name": r.name,
                            "recommended_shares": shares,
                            "recommended_amount": amt,
                            "reason": r.reason,
                            "target_weight": r.target_weight,
                            "current_weight": r.current_weight,
                        })

                    account_recommendations.append({
                        "account_id": acc.id,
                        "account_name": acc.account_name,
                        "broker": acc.broker,
                        "d_day": d_day,
                        "next_buy_date": next_dt.strftime("%Y-%m-%d") if next_dt else "",
                        "cycle_desc": c_desc or desc,
                        "already_invested_this_month": already_inv,
                        "total_recommended_amount": tot_rec if not already_inv else 0,
                        "items": acc_rec_items,
                    })

                except Exception as e:
                    logger.debug(f"계좌 [{acc.account_name}] 개별 요약, 종목 및 추천 집계 생략: {e}")

            # 전체 계좌 통합 포지션, 요약 및 매수 추천 집계 (account_id=None)
            positions_raw = self.portfolio_service.get_positions(account_id=None)
            summary_raw = self.portfolio_service.get_summary(positions_raw, account_id=None)
            rec_res_u = self.recommendation_service.calculate_recommendations(
                account_id=None, auto_save=False
            )
            rec_sum_u = rec_res_u.get("summary", {})
            recs_raw_u = rec_res_u.get("recommendations", [])
            already_inv_u = rec_sum_u.get("already_invested_in_cycle", False)

            def_acc = self.repo.get_default_account()
            if def_acc:
                next_dt_u, d_day_u, desc_u = calculate_next_investment_date(
                    getattr(def_acc, "buy_cycle_type", "monthly"),
                    getattr(def_acc, "buy_cycle_detail", "25"),
                )
            else:
                next_dt_u, d_day_u, desc_u = None, None, "수시 매수"

            unified_rec_items = []
            for r in recs_raw_u:
                shares = int(r.recommended_buy // r.current_price) if (r.current_price > 0 and not already_inv_u) else 0
                amt = r.recommended_buy if not already_inv_u else 0
                unified_rec_items.append({
                    "ticker": r.ticker,
                    "name": r.name,
                    "recommended_shares": shares,
                    "recommended_amount": amt,
                    "reason": r.reason,
                    "target_weight": r.target_weight,
                    "current_weight": r.current_weight,
                })

            recommendations = {
                "d_day": d_day_u,
                "next_buy_date": next_dt_u.strftime("%Y-%m-%d") if next_dt_u else "",
                "cycle_desc": rec_sum_u.get("cycle_desc", desc_u),
                "already_invested_this_month": already_inv_u,
                "total_recommended_amount": rec_sum_u.get("total_recommended_buy", 0) if not already_inv_u else 0,
                "items": unified_rec_items,
            }

            # 포트폴리오 요약 데이터 딕셔너리화
            summary = {
                "total_eval": getattr(summary_raw, "total_current_value", 0),
                "total_cost": getattr(summary_raw, "total_invested", 0),
                "total_pl": getattr(summary_raw, "total_pnl", getattr(summary_raw, "total_unrealized_pnl", 0)),
                "total_pl_pct": getattr(summary_raw, "total_roi", 0.0) * 100.0,
                "cash_balance": getattr(summary_raw, "remaining_cash", 0),
            }

            # 1-1. 전체 등록된 종목(목표 ETF + 보유 종목 + 설정 ETF) 맵 구성
            target_etfs = self.portfolio_service.get_target_etfs(account_id=None)
            registered_etfs_map: Dict[str, ETFConfig] = {}
            for e in target_etfs:
                registered_etfs_map[e.ticker] = e
            for e in self.config.etfs:
                if e.ticker not in registered_etfs_map:
                    registered_etfs_map[e.ticker] = e

            total_val = summary["total_eval"] or 1.0

            positions = []
            # 1) 실제 보유 종목 (수량 > 0)
            if isinstance(positions_raw, dict):
                for ticker, pos in positions_raw.items():
                    if pos.quantity <= 0:
                        continue
                    cur_w = (pos.current_value / total_val) if total_val > 0 else 0.0
                    t_weight = registered_etfs_map.get(ticker, ETFConfig(ticker, "", 0.0)).target_weight
                    positions.append({
                        "ticker": ticker,
                        "name": pos.name or ticker,
                        "shares": pos.quantity,
                        "current_price": pos.current_price,
                        "eval_amount": pos.current_value,
                        "pl_pct": pos.unrealized_roi * 100.0,
                        "current_weight": cur_w,
                        "target_weight": t_weight,
                    })
            elif isinstance(positions_raw, list):
                positions = positions_raw

            # 2) 등록된 목표 ETF 중 아직 수량이 0인 종목도 등록 종목 목록에 포함
            held_tickers = {p["ticker"] for p in positions}
            for ticker, etf in registered_etfs_map.items():
                if ticker not in held_tickers and etf.target_weight > 0:
                    latest_p = self.repo.get_latest_price(ticker)
                    cur_p = latest_p.close_price if latest_p else 0.0
                    positions.append({
                        "ticker": ticker,
                        "name": etf.name or ticker,
                        "shares": 0,
                        "current_price": cur_p,
                        "eval_amount": 0.0,
                        "pl_pct": 0.0,
                        "current_weight": 0.0,
                        "target_weight": etf.target_weight,
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
                        chg_pct = ((latest.close_price - prev_close) / prev_close) * 100.0
                    elif latest.open_price and latest.open_price > 0:
                        chg_pct = ((latest.close_price - latest.open_price) / latest.open_price) * 100.0
                    market_indices["KODEX 200"] = {
                        "price": f"{latest.close_price:,.0f}원",
                        "change_pct": round(chg_pct, 2),
                    }
                
            # 3-1. 글로벌 10대 거시경제 지표 및 5일 트렌드 데이터 수집
            macro_data = {}
            macro_summary = ""
            try:
                macro_data = self.macro_service.fetch_all_macro_data()
                macro_summary = self.macro_service.build_summary_for_gemini(macro_data)
                logger.info("글로벌 10대 매크로 지표 및 5일 트렌드 데이터 수집 완료")
            except Exception as e:
                logger.warning(f"매크로 10대 지표 수집 중 오류 (생략 진행): {e}")

            # 4. Google Gemini AI 매크로 투자 가이드 생성 (활성화된 경우)
            gemini_analysis = {}
            if getattr(self.config.morning_report, "gemini_enabled", True) and self.gemini_service.is_configured():
                try:
                    logger.info("Google Gemini AI 매크로 투자 가이드 생성 요청 중...")
                    gemini_analysis = self.gemini_service.generate_macro_investment_guide({
                        "account_name": account_name,
                        "summary": summary,
                        "recommendations": recommendations,
                        "positions": positions,
                        "news": news_items,
                        "market_indices": market_indices,
                        "macro_summary": macro_summary,
                    })
                except Exception as e:
                    logger.warning(f"Gemini AI 가이드 생성 중 오류 (기본 룰로 대체): {e}")

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
                "gemini_analysis": gemini_analysis,
            }

            # 5. 모바일 반응형 HTML 생성
            html_file = self.html_generator.generate_html(report_data)
            logger.info(f"모닝 리포트 HTML 생성 완료: {html_file}")

            # 웹 URL 결정 (카카오톡 버튼은 file:// 링크를 지원하지 않으며 반드시 http/https 여야 합니다)
            pages_env = os.getenv("GITHUB_PAGES_BASE_URL", "").strip().rstrip("/")
            gh_repo = getattr(self.config.morning_report, "github_repo", "").strip() or os.getenv("GITHUB_REPOSITORY", "").strip()
            if "github.com/" in gh_repo:
                gh_repo = gh_repo.split("github.com/")[1].strip("/").removesuffix(".git")

            if pages_env:
                report_web_url = f"{pages_env}/"
            elif gh_repo and "/" in gh_repo:
                parts = gh_repo.split("/")
                owner, repo = parts[0].strip().lower(), parts[1].strip()
                report_web_url = f"https://{owner}.github.io/{repo}/"
            else:
                # 기본 fallback 웹 URL (GitHub Pages)
                report_web_url = "https://taewook-3196.github.io/RetirementPortfolio/"

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

            # Pages 배포 후 카카오톡 분리 발송을 위해 페이로드 캐싱
            try:
                payload_cache = get_project_root() / "exports" / ".kakao_payload.json"
                payload_cache.parent.mkdir(parents=True, exist_ok=True)
                import json
                payload_cache.write_text(
                    json.dumps({"summary_text": summary_text, "report_web_url": report_web_url}, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
            except Exception as e:
                logger.warning(f"카카오 페이로드 캐시 저장 실패: {e}")

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

        total_eval = summary.get("total_eval", 0)
        total_pl = summary.get("total_pl", 0)
        total_pl_pct = summary.get("total_pl_pct", 0.0)
        sign = "+" if total_pl > 0 else ""

        d_day = recommendations.get("d_day", None)
        already_invested = recommendations.get("already_invested_this_month", False)
        rec_amt = recommendations.get("total_recommended_amount", 0)

        if already_invested:
            guide_text = "이번 주기 투자 완료 (비중 안정적 유지 중)"
        elif d_day == 0:
            guide_text = f"🚨 오늘 매수 D-Day! (추천: {rec_amt:,.0f}원)"
        elif d_day is not None:
            guide_text = f"매수 D-{d_day}일 남음 (예정: {recommendations.get('next_buy_date', '')})"
        else:
            guide_text = f"추천 매수액 {rec_amt:,.0f}원"

        lines = [
            f"🌅 [포트폴리오 모닝 리포트] {date_str} ({weekday_kr})",
            f"• 계좌: {account_name}",
            f"• 총자산: {total_eval:,.0f}원 ({sign}{total_pl_pct:.2f}%)",
        ]

        # 다중 계좌 등록 시 계좌별 요약 한 줄 표시
        if account_summaries and len(account_summaries) > 1:
            acc_strs = []
            for a in account_summaries:
                s_sign = "+" if a["total_pl"] > 0 else ""
                acc_strs.append(f"{a['name']} {a['total_eval']/10000:,.0f}만({s_sign}{a['total_pl_pct']:.1f}%)")
            lines.append(f"• 계좌별: {' | '.join(acc_strs)}")

        # 계좌별 투자 가이드 및 D-Day 표출
        if account_recommendations and len(account_recommendations) > 1:
            g_lines = []
            for ar in account_recommendations:
                ar_name = ar.get("account_name", "")
                ar_already = ar.get("already_invested_this_month", False)
                ar_dday = ar.get("d_day")
                ar_next = ar.get("next_buy_date", "")
                if ar_already:
                    g_lines.append(f"{ar_name}: 완료")
                elif ar_dday == 0:
                    g_lines.append(f"{ar_name}: 🚨D-Day")
                elif ar_dday is not None:
                    g_lines.append(f"{ar_name}: D-{ar_dday}({ar_next})")
                else:
                    g_lines.append(f"{ar_name}: 수시")
            lines.append(f"• 매수주기: {' | '.join(g_lines)}")
        else:
            lines.append(f"• 투자 가이드: {guide_text}")

        # 10대 글로벌 매크로 및 트렌드 요약 (미국 3대, 국내 2대, 환율/유가/금리, PCE/고용)
        if macro_data:
            try:
                macro_lines = self.macro_service.build_kakao_macro_lines(macro_data)
                if macro_lines:
                    lines.append("")
                    lines.extend(macro_lines)
            except Exception as e:
                logger.debug(f"카카오 매크로 라인 생성 생략: {e}")

        # Gemini AI 한 줄 시황이 있을 경우 최우선 하이라이트 표시 (투자 성향 배지 포함)
        if gemini_analysis and gemini_analysis.get("success") and gemini_analysis.get("one_line_summary"):
            ai_take = gemini_analysis.get("one_line_summary").strip()
            stance_badge = gemini_analysis.get("stance_badge")
            if stance_badge:
                lines.append(f"\n• 🤖 AI 시황 [{stance_badge}]: {ai_take}")
            else:
                lines.append(f"\n• 🤖 AI 시황: {ai_take}")

        # 등록 및 보유 종목 세부 현황 (다중 계좌 시 계좌별 그룹화 표출)
        if account_groups and len(account_groups) > 1:
            total_stocks = sum(len(ag.get("positions", [])) for ag in account_groups)
            lines.append(f"\n📋 계좌별 등록·보유 종목 현황 ({total_stocks}개):")
            for ag in account_groups:
                ag_name = ag.get("account_name", "")
                ag_pos = ag.get("positions", [])
                if not ag_pos:
                    continue
                ag_pct = ag.get("total_pl_pct", 0.0)
                ag_sign = "+" if ag_pct > 0 else ""
                lines.append(f"\n[{ag_name}] ({ag_sign}{ag_pct:.1f}%)")
                for p in ag_pos:
                    p_name = p.get("name", "")
                    p_price = p.get("current_price", 0)
                    p_pl = p.get("pl_pct", 0.0)
                    p_cur_w = p.get("current_weight", 0.0) * 100
                    p_tgt_w = p.get("target_weight", 0.0) * 100
                    p_shares = p.get("shares", 0)
                    p_sign = "+" if p_pl > 0 else ""

                    if p_shares > 0:
                        line = f"• {p_name}: {p_price:,.0f}원 ({p_sign}{p_pl:.1f}% | 비중 {p_cur_w:.1f}%)"
                    else:
                        line = f"• {p_name}: {p_price:,.0f}원 (미보유 | 목표 {p_tgt_w:.1f}%)"

                    # 1000자 초과 방지 체크
                    if sum(len(l) for l in lines) + len(line) > 900:
                        lines.append("• ... (상세 종목은 모바일 리포트에서 확인)")
                        break
                    lines.append(line)
        elif positions:
            lines.append(f"\n📋 전체 등록 종목 현황 ({len(positions)}개):")
            for p in positions:
                p_name = p.get("name", "")
                p_price = p.get("current_price", 0)
                p_pl = p.get("pl_pct", 0.0)
                p_cur_w = p.get("current_weight", 0.0) * 100
                p_tgt_w = p.get("target_weight", 0.0) * 100
                p_shares = p.get("shares", 0)
                p_sign = "+" if p_pl > 0 else ""

                if p_shares > 0:
                    line = f"• {p_name}: {p_price:,.0f}원 ({p_sign}{p_pl:.1f}% | 비중 {p_cur_w:.1f}%)"
                else:
                    line = f"• {p_name}: {p_price:,.0f}원 (미보유 | 목표 {p_tgt_w:.1f}%)"

                if sum(len(l) for l in lines) + len(line) > 900:
                    lines.append("• ... (상세 종목은 모바일 리포트에서 확인)")
                    break
                lines.append(line)

        # 추천 종목 (다중 계좌 시 계좌별 그룹화 표출)
        if account_recommendations and len(account_recommendations) > 1:
            has_rec = False
            rec_blocks = []
            for ar in account_recommendations:
                ar_name = ar.get("account_name", "")
                ar_items = [it for it in ar.get("items", []) if it.get("recommended_shares", 0) > 0]
                if ar_items:
                    has_rec = True
                    rec_blocks.append(f"[{ar_name}]")
                    for it in ar_items:
                        rec_blocks.append(f"• {it.get('name')} (+{it.get('recommended_shares'):,}주)")
            if has_rec:
                lines.append("\n🎯 계좌별 추천 매수:")
                lines.extend(rec_blocks)
            else:
                lines.append("\n🎯 이번 주기 추천 매수: 전 계좌 비중 균형 유지 중")
        else:
            items = recommendations.get("items", [])
            rec_items = [it for it in items if it.get("recommended_shares", 0) > 0]
            if rec_items:
                lines.append(f"\n🎯 이번 주기 추천 매수 ({len(rec_items)}종목):")
                for it in rec_items:
                    s = it.get("recommended_shares", 0)
                    lines.append(f"• {it.get('name')} (+{s:,}주)")
            elif not already_invested:
                lines.append("\n🎯 이번 주기 추천 매수: 전 등록 종목 비중 균형 유지 중")

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
            report_web_url = data.get("report_web_url", "https://taewook-3196.github.io/RetirementPortfolio/")
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
