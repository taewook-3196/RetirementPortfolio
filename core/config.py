"""
core/config.py
config.yaml 설정 파일을 로드하고 유효성을 검증하며, GUI 및 전략 모듈에 설정 객체를 제공합니다.
"""

from __future__ import annotations
import os
import yaml
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any
from pathlib import Path
from dotenv import load_dotenv
from core.paths import get_config_path

# .env 환경변수 자동 로드
load_dotenv()


@dataclass
class ETFConfig:
    ticker: str
    name: str
    target_weight: float
    dividend_yield: float = 0.0

    def validate(self) -> None:
        if not self.ticker or not str(self.ticker).strip():
            raise ValueError("ETF 종목코드는 빈 값일 수 없습니다.")
        if not (0.0 <= self.target_weight <= 1.0):
            raise ValueError(f"목표비중은 0.0 이상 1.0 이하이어야 합니다: {self.target_weight}")


@dataclass
class WatchlistConfig:
    ticker: str
    name: str

    def validate(self) -> None:
        if not self.ticker or not str(self.ticker).strip():
            raise ValueError("관심 종목코드는 빈 값일 수 없습니다.")


@dataclass
class DrawdownTier:
    min_drawdown: float
    max_drawdown: float
    additional_buy: int
    score: int


@dataclass
class MorningReportConfig:
    enabled: bool = False
    send_time: str = "07:00"
    kakao_rest_api_key: str = ""
    kakao_access_token: str = ""
    kakao_refresh_token: str = ""
    include_ai_briefing: bool = True
    include_news: bool = True
    include_summary: bool = True
    include_positions: bool = True
    include_market_indices: bool = True
    web_report_mode: str = "local_browser"
    # GitHub Actions 클라우드 원격 연동
    github_repo: str = ""              # 예: "owner/repo"
    github_token: str = ""             # GitHub Personal Access Token (PAT)
    github_workflow_id: str = "morning_report.yml"
    github_cloud_enabled: bool = False # 클라우드 워크플로우 활성화 여부
    # Google Gemini AI 연동 설정
    gemini_enabled: bool = True
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    ai_investment_stance: str = "balanced"  # very_conservative | conservative | balanced | aggressive | very_aggressive


@dataclass
class AppConfig:
    data_source: str = "krx"
    initial_capital: int = 100000000
    base_monthly: int = 10000000
    max_additional_monthly: int = 15000000
    etfs: List[ETFConfig] = field(default_factory=list)
    watchlist: List[WatchlistConfig] = field(default_factory=list)
    drawdown_tiers: List[DrawdownTier] = field(default_factory=list)
    priority_weights: Dict[str, float] = field(
        default_factory=lambda: {"drawdown": 0.7, "weight_gap": 0.3}
    )
    news_filter_mode: str = "all"  # 'all' (전체 경제 뉴스) or 'portfolio_only' (내 종목 뉴스만)
    show_splash_screen: bool = True  # 프로그램 시작 시 황금복돼지 스플래시 인트로 표출 여부
    morning_report: MorningReportConfig = field(default_factory=MorningReportConfig)

    def validate(self) -> None:
        if self.initial_capital < 0:
            raise ValueError("초기 투자금은 0원 이상이어야 합니다.")
        if self.base_monthly < 0:
            raise ValueError("월 기본 매수금은 0원 이상이어야 합니다.")
        if self.max_additional_monthly < 0:
            raise ValueError("월 최대 추가매수금은 0원 이상이어야 합니다.")
        if not self.etfs:
            raise ValueError("최소 1개 이상의 ETF가 설정되어야 합니다.")

        tickers = set()
        total_weight = 0.0
        for etf in self.etfs:
            etf.validate()
            if etf.ticker in tickers:
                raise ValueError(f"중복된 종목코드가 존재합니다: {etf.ticker}")
            tickers.add(etf.ticker)
            total_weight += etf.target_weight

        if total_weight > 1.0 + 0.001:
            raise ValueError(f"목표비중의 합계는 100%를 초과할 수 없습니다. (현재 합계: {round(total_weight * 100, 2)}%)")

        watch_tickers = set()
        for w in self.watchlist:
            w.validate()
            if w.ticker in watch_tickers:
                raise ValueError(f"중복된 관심 종목코드가 존재합니다: {w.ticker}")
            watch_tickers.add(w.ticker)


def get_default_config() -> AppConfig:
    """기본 AppConfig 인스턴스를 반환합니다."""
    return AppConfig(
        data_source="krx",
        initial_capital=100000000,
        base_monthly=10000000,
        max_additional_monthly=15000000,
        etfs=[
            ETFConfig(ticker="442560", name="RISE TDF2040액티브", target_weight=0.60, dividend_yield=0.025),
            ETFConfig(ticker="488500", name="TIGER 미국S&P500동일가중", target_weight=0.25, dividend_yield=0.015),
            ETFConfig(ticker="494840", name="TIGER 미국나스닥TOP10", target_weight=0.15, dividend_yield=0.010),
        ],
        watchlist=[
            WatchlistConfig(ticker="069500", name="KODEX 200"),
        ],
        drawdown_tiers=[
            DrawdownTier(min_drawdown=0.00, max_drawdown=-0.05, additional_buy=0, score=0),
            DrawdownTier(min_drawdown=-0.05, max_drawdown=-0.10, additional_buy=2000000, score=1),
            DrawdownTier(min_drawdown=-0.10, max_drawdown=-0.15, additional_buy=5000000, score=2),
            DrawdownTier(min_drawdown=-0.15, max_drawdown=-0.20, additional_buy=10000000, score=3),
            DrawdownTier(min_drawdown=-0.20, max_drawdown=-1.00, additional_buy=15000000, score=4),
        ],
        priority_weights={"drawdown": 0.7, "weight_gap": 0.3},
        show_splash_screen=True,
    )


def load_config(config_path: Path | None = None) -> AppConfig:
    """config.yaml 파일을 읽어 AppConfig 객체로 변환 및 검증합니다."""
    path = config_path or get_config_path()
    if not path.exists():
        cfg = get_default_config()
        save_config(cfg, path)
        return cfg

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    etfs = [
        ETFConfig(
            ticker=str(item.get("ticker", "")).strip(),
            name=str(item.get("name", "")).strip(),
            target_weight=float(item.get("target_weight", 0.0)),
            dividend_yield=float(item.get("dividend_yield", 0.0)),
        )
        for item in data.get("etfs", [])
    ]

    watchlist = [
        WatchlistConfig(
            ticker=str(item.get("ticker", "")).strip(),
            name=str(item.get("name", "")).strip(),
        )
        for item in data.get("watchlist", [])
    ]

    drawdown_tiers = [
        DrawdownTier(
            min_drawdown=float(t.get("min_drawdown", 0.0)),
            max_drawdown=float(t.get("max_drawdown", 0.0)),
            additional_buy=int(t.get("additional_buy", 0)),
            score=int(t.get("score", 0)),
        )
        for t in data.get("drawdown_tiers", [])
    ]

    m_rep_data = data.get("morning_report", {})
    env_gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    env_gemini_model = os.getenv("GEMINI_MODEL", "").strip()

    cfg_gemini_key = str(m_rep_data.get("gemini_api_key", "")).strip() or env_gemini_key
    cfg_gemini_model = env_gemini_model or str(m_rep_data.get("gemini_model", "gemini-3.8-flash")).strip() or "gemini-3.8-flash"

    cfg_kakao_rest = str(m_rep_data.get("kakao_rest_api_key", "")).strip() or os.getenv("KAKAO_REST_API_KEY", "").strip()
    cfg_kakao_access = str(m_rep_data.get("kakao_access_token", "")).strip() or os.getenv("KAKAO_ACCESS_TOKEN", "").strip()
    cfg_kakao_refresh = str(m_rep_data.get("kakao_refresh_token", "")).strip() or os.getenv("KAKAO_REFRESH_TOKEN", "").strip()
    cfg_gh_repo = str(m_rep_data.get("github_repo", "")).strip() or os.getenv("GITHUB_REPOSITORY", "").strip()
    cfg_gh_token = str(m_rep_data.get("github_token", "")).strip() or os.getenv("GITHUB_TOKEN", "").strip()

    cfg_ai_stance = str(m_rep_data.get("ai_investment_stance", "")).strip() or os.getenv("AI_INVESTMENT_STANCE", "").strip() or "balanced"
    if cfg_ai_stance not in ("very_conservative", "conservative", "balanced", "aggressive", "very_aggressive"):
        cfg_ai_stance = "balanced"

    morning_report = MorningReportConfig(
        enabled=bool(m_rep_data.get("enabled", False)),
        send_time=str(m_rep_data.get("send_time", "07:00")).strip(),
        kakao_rest_api_key=cfg_kakao_rest,
        kakao_access_token=cfg_kakao_access,
        kakao_refresh_token=cfg_kakao_refresh,
        include_ai_briefing=bool(m_rep_data.get("include_ai_briefing", True)),
        include_news=bool(m_rep_data.get("include_news", True)),
        include_summary=bool(m_rep_data.get("include_summary", True)),
        include_positions=bool(m_rep_data.get("include_positions", True)),
        include_market_indices=bool(m_rep_data.get("include_market_indices", True)),
        web_report_mode=str(m_rep_data.get("web_report_mode", "local_browser")).strip(),
        github_repo=cfg_gh_repo,
        github_token=cfg_gh_token,
        github_workflow_id=str(m_rep_data.get("github_workflow_id", "morning_report.yml")).strip(),
        github_cloud_enabled=bool(m_rep_data.get("github_cloud_enabled", False)),
        gemini_enabled=bool(m_rep_data.get("gemini_enabled", True)),
        gemini_api_key=cfg_gemini_key,
        gemini_model=cfg_gemini_model,
        ai_investment_stance=cfg_ai_stance,
    )

    cfg = AppConfig(
        data_source=data.get("data_source", "krx"),
        initial_capital=int(data.get("initial_capital", 100000000)),
        base_monthly=int(data.get("base_monthly", 10000000)),
        max_additional_monthly=int(data.get("max_additional_monthly", 15000000)),
        etfs=etfs,
        watchlist=watchlist,
        drawdown_tiers=drawdown_tiers,
        priority_weights=data.get("priority_weights", {"drawdown": 0.7, "weight_gap": 0.3}),
        news_filter_mode=str(data.get("news_filter_mode", "all")).strip(),
        show_splash_screen=bool(data.get("show_splash_screen", True)),
        morning_report=morning_report,
    )
    cfg.validate()
    return cfg


def save_config(config: AppConfig, config_path: Path | None = None) -> None:
    """AppConfig 객체를 config.yaml 파일에 직렬화하여 저장합니다."""
    config.validate()
    path = config_path or get_config_path()

    raw_data = {
        "data_source": config.data_source,
        "initial_capital": config.initial_capital,
        "base_monthly": config.base_monthly,
        "max_additional_monthly": config.max_additional_monthly,
        "news_filter_mode": getattr(config, "news_filter_mode", "all"),
        "show_splash_screen": getattr(config, "show_splash_screen", True),
        "morning_report": asdict(getattr(config, "morning_report", MorningReportConfig())),
        "etfs": [asdict(e) for e in config.etfs],
        "watchlist": [asdict(w) for w in config.watchlist],
        "drawdown_tiers": [asdict(t) for t in config.drawdown_tiers],
        "priority_weights": config.priority_weights,
    }

    # 기존에 저장된 유효한 인증 토큰(카카오, 깃허브, 제미나이)이 빈 문자열로 덮어써지는 사고 방지
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                old_data = yaml.safe_load(f) or {}
            old_m = old_data.get("morning_report", {})
            cur_m = raw_data.get("morning_report", {})
            for sensitive_key in [
                "kakao_rest_api_key",
                "kakao_access_token",
                "kakao_refresh_token",
                "github_repo",
                "github_token",
                "gemini_api_key",
            ]:
                if not cur_m.get(sensitive_key) and old_m.get(sensitive_key):
                    cur_m[sensitive_key] = old_m[sensitive_key]
        except Exception:
            pass

    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(raw_data, f, allow_unicode=True, sort_keys=False)
