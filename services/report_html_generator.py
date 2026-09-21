"""
services/report_html_generator.py
스마트폰 화면에 최적화된 프리미엄 다크모드 모바일 웹 리포트 HTML 생성기.
- 반응형 웹 디자인 (Mobile-First CSS, Glassmorphism, Gradient Badges)
- 계좌 자산 총괄 KPI, AI 투자 가이드, 포트폴리오 종목 현황, 관심/보유 종목 뉴스 브리핑 지원
- MorningReportConfig 설정에 따른 섹션별 On/Off 조건부 렌더링
"""

from __future__ import annotations
import re
import logging
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from core.paths import get_report_dir
from core.config import MorningReportConfig

logger = logging.getLogger("RetirementPortfolio.ReportHtmlGenerator")


class ReportHtmlGenerator:
    """모닝 모바일 웹 리포트 HTML 생성 클래스"""

    def __init__(self, config: Optional[MorningReportConfig] = None):
        self.config = config or MorningReportConfig()

    def generate_html(
        self,
        report_data: Dict[str, Any],
        output_filename: Optional[str] = None,
    ) -> Path:
        """
        주어진 리포트 데이터(자산 요약, AI 추천, 종목, 뉴스, 지수)를 바탕으로
        모바일 반응형 웹 리포트 HTML 파일을 생성하여 저장하고 파일 경로를 반환합니다.
        """
        now = datetime.datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M")
        weekday_kr = ["월", "화", "수", "목", "금", "토", "일"][now.weekday()]

        if not output_filename:
            output_filename = f"morning_report_{now.strftime('%Y%m%d')}.html"

        report_dir = get_report_dir()
        file_path = report_dir / output_filename

        # 데이터 추출
        summary = report_data.get("summary", {})
        recommendations = report_data.get("recommendations", {})
        positions = report_data.get("positions", [])
        news_items = report_data.get("news", [])
        market_indices = report_data.get("market_indices", {})
        macro_indicators = report_data.get("macro_indicators", {})
        account_name = report_data.get("account_name", "전체 계좌 통합")

        # 섹션별 HTML 조각 생성
        account_summaries = report_data.get("account_summaries", [])
        account_groups = report_data.get("account_groups", [])
        account_recommendations = report_data.get("account_recommendations", [])
        gemini_analysis = report_data.get("gemini_analysis", {})
        gemini_html = self._render_gemini_section(gemini_analysis) if gemini_analysis and gemini_analysis.get("success") else ""
        summary_html = self._render_summary_section(summary, account_summaries) if self.config.include_summary else ""
        ai_briefing_html = self._render_ai_briefing_section(recommendations, summary, account_recommendations=account_recommendations) if self.config.include_ai_briefing else ""
        positions_html = self._render_positions_section(positions, account_groups=account_groups) if self.config.include_positions else ""
        news_html = self._render_news_section(news_items) if self.config.include_news else ""
        
        # 10대 글로벌 매크로 지표 대시보드 (또는 기존 시장지수 fallback)
        if self.config.include_market_indices:
            if macro_indicators and (macro_indicators.get("raw_items") or macro_indicators.get("fundamentals")):
                market_html = self._render_macro_dashboard_section(macro_indicators)
            else:
                market_html = self._render_market_section(market_indices)
        else:
            market_html = ""

        html_content = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
    <title>모닝 포트폴리오 리포트 | {date_str}</title>
    <style>
        :root {{
            --bg-base: #0b0f19;
            --bg-card: rgba(26, 34, 52, 0.85);
            --bg-card-sub: rgba(36, 48, 74, 0.6);
            --border-subtle: rgba(255, 255, 255, 0.08);
            --border-accent: rgba(99, 102, 241, 0.25);
            --text-main: #f1f5f9;
            --text-muted: #94a3b8;
            --text-dim: #64748b;
            --accent-primary: #6366f1;
            --accent-success: #10b981;
            --accent-danger: #ef4444;
            --accent-warning: #f59e0b;
            --accent-cyan: #06b6d4;
            --gradient-header: linear-gradient(135deg, #1e1b4b 0%, #312e81 50%, #4338ca 100%);
            --gradient-card: linear-gradient(180deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.8) 100%);
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            -webkit-tap-highlight-color: transparent;
        }}

        body {{
            background-color: var(--bg-base);
            color: var(--text-main);
            font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Pretendard", "Segoe UI", Roboto, sans-serif;
            line-height: 1.5;
            letter-spacing: -0.015em;
            padding: 0 0 40px 0;
            background-image: 
                radial-gradient(circle at 15% 15%, rgba(99, 102, 241, 0.12) 0%, transparent 40%),
                radial-gradient(circle at 85% 65%, rgba(16, 185, 129, 0.08) 0%, transparent 45%);
            background-attachment: fixed;
        }}

        .container {{
            max-width: 520px;
            margin: 0 auto;
            padding: 0 16px;
        }}

        /* 헤더 스타일 */
        .header {{
            padding: 28px 16px 20px 16px;
            text-align: center;
            position: relative;
        }}

        .header-badge {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(99, 102, 241, 0.15);
            border: 1px solid rgba(99, 102, 241, 0.3);
            color: #a5b4fc;
            padding: 4px 12px;
            border-radius: 9999px;
            font-size: 12px;
            font-weight: 600;
            margin-bottom: 12px;
            text-transform: uppercase;
        }}

        .header-title {{
            font-size: 24px;
            font-weight: 800;
            letter-spacing: -0.03em;
            background: linear-gradient(135deg, #ffffff 0%, #cbd5e1 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 6px;
        }}

        .header-meta {{
            font-size: 13px;
            color: var(--text-muted);
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }}

        .acc-pill {{
            background: rgba(255, 255, 255, 0.08);
            padding: 2px 8px;
            border-radius: 6px;
            font-weight: 500;
            color: #e2e8f0;
        }}

        /* 공통 카드 */
        .card {{
            background: var(--bg-card);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid var(--border-subtle);
            border-radius: 18px;
            padding: 20px;
            margin-bottom: 18px;
            box-shadow: 0 8px 30px rgba(0, 0, 0, 0.35);
        }}

        .card-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 16px;
        }}

        .card-title-group {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .card-icon {{
            font-size: 18px;
        }}

        .card-title {{
            font-size: 16px;
            font-weight: 700;
            color: #f8fafc;
        }}

        .badge {{
            font-size: 11px;
            font-weight: 700;
            padding: 3px 8px;
            border-radius: 6px;
        }}

        .badge-success {{
            background: rgba(16, 185, 129, 0.18);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.3);
        }}

        .badge-danger {{
            background: rgba(239, 68, 68, 0.18);
            color: #f87171;
            border: 1px solid rgba(239, 68, 68, 0.3);
        }}

        .badge-info {{
            background: rgba(99, 102, 241, 0.18);
            color: #a5b4fc;
            border: 1px solid rgba(99, 102, 241, 0.3);
        }}

        .badge-warning {{
            background: rgba(245, 158, 11, 0.18);
            color: #fbbf24;
            border: 1px solid rgba(245, 158, 11, 0.3);
        }}

        /* KPI 요약 스타일 */
        .kpi-main {{
            text-align: center;
            padding: 12px 0 16px 0;
            border-bottom: 1px solid var(--border-subtle);
            margin-bottom: 16px;
        }}

        .kpi-label {{
            font-size: 13px;
            color: var(--text-muted);
            margin-bottom: 4px;
        }}

        .kpi-value-huge {{
            font-size: 32px;
            font-weight: 800;
            letter-spacing: -0.04em;
            color: #ffffff;
        }}

        .kpi-pl-group {{
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            margin-top: 6px;
            font-size: 14px;
            font-weight: 600;
        }}

        .pl-plus {{ color: #f87171; }}
        .pl-minus {{ color: #60a5fa; }}
        .pl-zero {{ color: var(--text-muted); }}

        .kpi-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
        }}

        .kpi-sub-item {{
            background: var(--bg-card-sub);
            padding: 12px 14px;
            border-radius: 12px;
            border: 1px solid var(--border-subtle);
        }}

        .kpi-sub-label {{
            font-size: 12px;
            color: var(--text-dim);
            margin-bottom: 4px;
        }}

        .kpi-sub-val {{
            font-size: 16px;
            font-weight: 700;
            color: #e2e8f0;
        }}

        /* AI 브리핑 카드 스타일 */
        .ai-guide-box {{
            background: linear-gradient(135deg, rgba(99, 102, 241, 0.15) 0%, rgba(59, 130, 246, 0.08) 100%);
            border: 1px solid rgba(99, 102, 241, 0.35);
            border-radius: 14px;
            padding: 16px;
            margin-bottom: 14px;
        }}

        .ai-guide-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 10px;
        }}

        .ai-dday-badge {{
            font-size: 13px;
            font-weight: 800;
            padding: 4px 10px;
            border-radius: 8px;
            background: #6366f1;
            color: #ffffff;
            box-shadow: 0 2px 8px rgba(99, 102, 241, 0.4);
        }}

        .ai-comment {{
            font-size: 14px;
            line-height: 1.6;
            color: #e2e8f0;
        }}

        .ai-comment strong {{
            color: #38bdf8;
        }}

        .recom-item-card {{
            background: var(--bg-card-sub);
            border: 1px solid var(--border-subtle);
            border-radius: 12px;
            padding: 12px 14px;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}

        .recom-info-name {{
            font-size: 14px;
            font-weight: 700;
            color: #f8fafc;
        }}

        .recom-info-ticker {{
            font-size: 11px;
            color: var(--text-dim);
        }}

        .recom-val-box {{
            text-align: right;
        }}

        .recom-shares {{
            font-size: 14px;
            font-weight: 700;
            color: #a5b4fc;
        }}

        .recom-amt {{
            font-size: 12px;
            color: var(--text-muted);
        }}

        /* 보유 종목 테이블/카드 */
        .pos-item {{
            padding: 12px 0;
            border-bottom: 1px solid var(--border-subtle);
        }}

        .pos-item:last-child {{
            border-bottom: none;
            padding-bottom: 0;
        }}

        .pos-item:first-child {{
            padding-top: 0;
        }}

        .pos-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 6px;
        }}

        .pos-name {{
            font-size: 14px;
            font-weight: 700;
            color: #f1f5f9;
        }}

        .pos-eval {{
            font-size: 14px;
            font-weight: 700;
            color: #ffffff;
        }}

        .pos-details {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-size: 12px;
            color: var(--text-muted);
        }}

        .progress-bar-bg {{
            height: 6px;
            background: rgba(255, 255, 255, 0.08);
            border-radius: 9999px;
            overflow: hidden;
            margin-top: 8px;
            position: relative;
        }}

        .progress-bar-fill {{
            height: 100%;
            background: linear-gradient(90deg, #6366f1, #38bdf8);
            border-radius: 9999px;
        }}

        /* 계좌별 보유종목 그룹 스타일 */
        .account-tabs {{
            display: flex;
            gap: 6px;
            overflow-x: auto;
            padding-bottom: 8px;
            margin-bottom: 12px;
            scrollbar-width: none;
            -webkit-overflow-scrolling: touch;
        }}

        .account-tabs::-webkit-scrollbar {{
            display: none;
        }}

        .account-tab-btn {{
            background: var(--bg-card-sub);
            border: 1px solid var(--border-subtle);
            color: var(--text-muted);
            padding: 6px 12px;
            border-radius: 8px;
            font-size: 11.5px;
            font-weight: 600;
            white-space: nowrap;
            cursor: pointer;
            transition: all 0.2s ease;
        }}

        .account-tab-btn:hover {{
            border-color: rgba(99, 102, 241, 0.4);
            color: #ffffff;
        }}

        .account-tab-btn.active {{
            background: linear-gradient(135deg, rgba(99, 102, 241, 0.3) 0%, rgba(59, 130, 246, 0.22) 100%);
            border-color: var(--accent-primary);
            color: #ffffff;
            font-weight: 700;
            box-shadow: 0 2px 8px rgba(99, 102, 241, 0.25);
        }}

        .account-pos-group {{
            background: rgba(15, 23, 42, 0.55);
            border: 1px solid var(--border-subtle);
            border-radius: 12px;
            padding: 12px 14px;
            margin-bottom: 14px;
            transition: opacity 0.2s ease;
        }}

        .account-pos-group:last-child {{
            margin-bottom: 0;
        }}

        .account-pos-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding-bottom: 8px;
            border-bottom: 1px solid var(--border-subtle);
            margin-bottom: 8px;
        }}

        .account-group-title {{
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .account-badge-pill {{
            font-size: 10px;
            font-weight: 700;
            padding: 2px 6px;
            border-radius: 4px;
            background: rgba(99, 102, 241, 0.2);
            color: #a5b4fc;
            border: 1px solid rgba(99, 102, 241, 0.35);
        }}

        .account-name-label {{
            font-size: 13.5px;
            font-weight: 700;
            color: #f8fafc;
        }}

        .account-broker-label {{
            font-size: 11px;
            color: var(--text-dim);
        }}

        .account-group-kpi {{
            text-align: right;
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .account-eval-amount {{
            font-size: 13px;
            font-weight: 700;
            color: #ffffff;
        }}

        .account-sub-meta {{
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 10.5px;
            color: var(--text-dim);
            margin-bottom: 8px;
            padding: 0 2px;
        }}

        /* AI briefing account tabs */
        .ai-tabs {{
            display: flex;
            gap: 6px;
            overflow-x: auto;
            padding-bottom: 8px;
            margin-bottom: 12px;
            scrollbar-width: none;
            -webkit-overflow-scrolling: touch;
        }}

        .ai-tabs::-webkit-scrollbar {{
            display: none;
        }}

        .ai-tab-btn {{
            background: var(--bg-card-sub);
            border: 1px solid var(--border-subtle);
            color: var(--text-muted);
            padding: 6px 12px;
            border-radius: 8px;
            font-size: 11.5px;
            font-weight: 600;
            white-space: nowrap;
            cursor: pointer;
            transition: all 0.2s ease;
        }}

        .ai-tab-btn:hover {{
            border-color: rgba(99, 102, 241, 0.4);
            color: #ffffff;
        }}

        .ai-tab-btn.active {{
            background: linear-gradient(135deg, rgba(99, 102, 241, 0.3) 0%, rgba(59, 130, 246, 0.22) 100%);
            border-color: var(--accent-primary);
            color: #ffffff;
            font-weight: 700;
            box-shadow: 0 2px 8px rgba(99, 102, 241, 0.25);
        }}

        .account-ai-group {{
            background: rgba(15, 23, 42, 0.55);
            border: 1px solid var(--border-subtle);
            border-radius: 12px;
            padding: 12px 14px;
            margin-bottom: 14px;
            transition: opacity 0.2s ease;
        }}

        .account-ai-group:last-child {{
            margin-bottom: 0;
        }}

        .account-ai-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding-bottom: 8px;
            border-bottom: 1px solid var(--border-subtle);
            margin-bottom: 10px;
        }}

        /* 뉴스 카드 스타일 */
        .news-item {{
            padding: 12px 0;
            border-bottom: 1px solid var(--border-subtle);
        }}

        .news-item:last-child {{
            border-bottom: none;
            padding-bottom: 0;
        }}

        .news-item:first-child {{
            padding-top: 0;
        }}

        .news-tag-box {{
            display: flex;
            align-items: center;
            gap: 6px;
            margin-bottom: 4px;
        }}

        .news-tag {{
            font-size: 10px;
            font-weight: 700;
            padding: 2px 6px;
            border-radius: 4px;
            background: rgba(99, 102, 241, 0.15);
            color: #818cf8;
            border: 1px solid rgba(99, 102, 241, 0.25);
        }}

        .news-media {{
            font-size: 11px;
            color: var(--text-dim);
        }}

        .news-title {{
            font-size: 14px;
            font-weight: 600;
            line-height: 1.45;
            color: #f1f5f9;
            text-decoration: none;
            display: block;
            margin-bottom: 4px;
            transition: color 0.2s;
        }}

        .news-title:hover {{
            color: #60a5fa;
        }}

        .news-time {{
            font-size: 11px;
            color: var(--text-dim);
        }}

        /* 시장 지표 바 */
        .market-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 8px;
        }}

        .market-item {{
            background: var(--bg-card-sub);
            padding: 10px 8px;
            border-radius: 10px;
            text-align: center;
            border: 1px solid var(--border-subtle);
        }}

        .market-name {{
            font-size: 11px;
            color: var(--text-dim);
            margin-bottom: 2px;
        }}

        .market-val {{
            font-size: 13px;
            font-weight: 700;
            color: #ffffff;
        }}

        .market-change {{
            font-size: 11px;
            font-weight: 600;
            margin-top: 2px;
        }}

        /* 10대 글로벌 매크로 대시보드 스타일 */
        .macro-subgroup {{
            margin-bottom: 12px;
        }}

        .macro-subgroup:last-child {{
            margin-bottom: 0;
        }}

        .macro-group-title {{
            font-size: 11.5px;
            font-weight: 700;
            color: #94a3b8;
            margin-bottom: 6px;
            display: flex;
            align-items: center;
            gap: 5px;
        }}

        .macro-grid-3 {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 6px;
        }}

        .macro-grid-2 {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 6px;
        }}

        .macro-card {{
            background: var(--bg-card-sub);
            border: 1px solid var(--border-subtle);
            border-radius: 10px;
            padding: 8px 8px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }}

        .macro-card-name {{
            font-size: 11px;
            font-weight: 600;
            color: #cbd5e1;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}

        .macro-card-val {{
            font-size: 13px;
            font-weight: 800;
            color: #ffffff;
            margin: 2px 0;
            letter-spacing: -0.02em;
        }}

        .macro-card-footer {{
            display: flex;
            flex-direction: column;
            gap: 2px;
        }}

        .trend-badge {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 9.5px;
            font-weight: 700;
            padding: 2px 5px;
            border-radius: 5px;
            line-height: 1.2;
            width: fit-content;
        }}

        .trend-badge-up {{
            background: rgba(248, 113, 113, 0.16);
            color: #f87171;
            border: 1px solid rgba(248, 113, 113, 0.35);
        }}

        .trend-badge-down {{
            background: rgba(96, 165, 250, 0.16);
            color: #60a5fa;
            border: 1px solid rgba(96, 165, 250, 0.35);
        }}

        .trend-badge-flat {{
            background: rgba(148, 163, 184, 0.15);
            color: #94a3b8;
            border: 1px solid rgba(148, 163, 184, 0.3);
        }}

        .macro-fund-item {{
            background: var(--bg-card-sub);
            border: 1px solid var(--border-subtle);
            border-radius: 10px;
            padding: 8px 10px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}

        .macro-fund-info {{
            display: flex;
            flex-direction: column;
            gap: 1px;
        }}

        .macro-fund-name {{
            font-size: 11.5px;
            font-weight: 700;
            color: #f1f5f9;
        }}

        .macro-fund-desc {{
            font-size: 10px;
            color: var(--text-dim);
        }}

        .macro-fund-valbox {{
            text-align: right;
            display: flex;
            flex-direction: column;
            align-items: flex-end;
            gap: 2px;
        }}

        .macro-fund-val {{
            font-size: 13px;
            font-weight: 800;
            color: #38bdf8;
        }}

        /* Gemini AI 섹션 전용 스타일 */
        .gemini-quote-box {{
            background: linear-gradient(135deg, rgba(99, 102, 241, 0.15) 0%, rgba(168, 85, 247, 0.12) 100%);
            border: 1px solid rgba(168, 85, 247, 0.35);
            border-radius: 12px;
            padding: 14px 16px;
            margin-bottom: 14px;
        }}

        .gemini-quote-text {{
            font-size: 14px;
            font-weight: 600;
            color: #f8fafc;
            line-height: 1.6;
        }}

        .gemini-block {{
            background: var(--bg-card-sub);
            border: 1px solid var(--border-subtle);
            border-radius: 12px;
            padding: 13px 15px;
            margin-bottom: 10px;
        }}

        .gemini-block-title {{
            font-size: 13px;
            font-weight: 700;
            color: #38bdf8;
            margin-bottom: 6px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}

        .gemini-block-content {{
            font-size: 13.5px;
            line-height: 1.65;
            color: #cbd5e1;
        }}

        .gemini-tag {{
            font-size: 11px;
            font-weight: 600;
            padding: 2px 7px;
            border-radius: 4px;
            background: rgba(56, 189, 248, 0.15);
            color: #38bdf8;
        }}

        /* 푸터 */
        .footer {{
            text-align: center;
            padding: 20px 16px 0 16px;
            font-size: 12px;
            color: var(--text-dim);
            line-height: 1.6;
        }}

        .footer p {{
            margin-bottom: 4px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- 상단 헤더 -->
        <header class="header">
            <div class="header-badge">🌅 Morning Portfolio Brief</div>
            <h1 class="header-title">오늘의 투자 리포트</h1>
            <div class="header-meta">
                <span>{date_str} ({weekday_kr}) {time_str}</span>
                <span>•</span>
                <span class="acc-pill">{account_name}</span>
            </div>
        </header>

        {market_html}
        {summary_html}
        {gemini_html}
        {ai_briefing_html}
        {positions_html}
        {news_html}

        <!-- 푸터 -->
        <footer class="footer">
            <p>퇴직연금 & 자산배분 스마트 포트폴리오 매니저</p>
            <p style="font-size: 11px; color: #475569;">본 리포트는 개인 자산관리 참고용이며 투자 권유가 아닙니다.</p>
        </footer>
    </div>
</body>
</html>
"""
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        # GitHub Pages 기본 엔드포인트 지원을 위해 index.html로도 함께 저장
        try:
            index_path = report_dir / "index.html"
            with open(index_path, "w", encoding="utf-8") as f:
                f.write(html_content)
        except Exception as e:
            logger.warning(f"index.html 저장 실패: {e}")

        return file_path

    def _render_summary_section(
        self,
        summary: Dict[str, Any],
        account_summaries: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """자산 총괄 KPI 카드 렌더링"""
        total_eval = summary.get("total_eval", 0)
        total_cost = summary.get("total_cost", 0)
        total_pl = summary.get("total_pl", 0)
        total_pl_pct = summary.get("total_pl_pct", 0.0)
        cash_balance = summary.get("cash_balance", 0)

        pl_class = "pl-plus" if total_pl > 0 else ("pl-minus" if total_pl < 0 else "pl-zero")
        pl_sign = "+" if total_pl > 0 else ""

        acc_breakdown_html = ""
        if account_summaries and len(account_summaries) > 1:
            pills = ""
            for a in account_summaries:
                a_name = a.get("name", "")
                a_eval = a.get("total_eval", 0)
                a_pct = a.get("total_pl_pct", 0.0)
                a_sign = "+" if a_pct > 0 else ""
                a_cls = "pl-plus" if a_pct > 0 else ("pl-minus" if a_pct < 0 else "pl-zero")
                pills += f"""
                <div style="background: rgba(15, 23, 42, 0.6); border: 1px solid var(--border-subtle); border-radius: 8px; padding: 6px 10px; font-size: 11.5px; display: flex; justify-content: space-between; align-items: center;">
                    <span style="color: #cbd5e1; font-weight: 600;">{a_name}</span>
                    <span><strong style="color: #ffffff;">{a_eval:,.0f}원</strong> <span class="{a_cls}" style="font-weight: 700;">({a_sign}{a_pct:.1f}%)</span></span>
                </div>
                """
            acc_breakdown_html = f"""
            <div style="margin-top: 12px; display: flex; flex-direction: column; gap: 5px;">
                <div style="font-size: 11px; font-weight: 700; color: #94a3b8;">🏢 등록 계좌별 현황</div>
                {pills}
            </div>
            """

        return f"""
        <section class="card">
            <div class="card-header">
                <div class="card-title-group">
                    <span class="card-icon">💰</span>
                    <h2 class="card-title">내 계좌 자산 총괄</h2>
                </div>
                <span class="badge { 'badge-success' if total_pl >= 0 else 'badge-danger' }">
                    {pl_sign}{total_pl_pct:.2f}%
                </span>
            </div>

            <div class="kpi-main">
                <div class="kpi-label">총 평가자산</div>
                <div class="kpi-value-huge">{total_eval:,.0f}원</div>
                <div class="kpi-pl-group">
                    <span class="kpi-label">평가손익:</span>
                    <span class="{pl_class}">{pl_sign}{total_pl:,.0f}원 ({pl_sign}{total_pl_pct:.2f}%)</span>
                </div>
            </div>

            <div class="kpi-grid">
                <div class="kpi-sub-item">
                    <div class="kpi-sub-label">총 투자원금</div>
                    <div class="kpi-sub-val">{total_cost:,.0f}원</div>
                </div>
                <div class="kpi-sub-item">
                    <div class="kpi-sub-label">예수금 (현금 잔고)</div>
                    <div class="kpi-sub-val">{cash_balance:,.0f}원</div>
                </div>
            </div>
            {acc_breakdown_html}
        </section>
        """

    def _render_ai_briefing_section(
        self,
        recommendations: Dict[str, Any],
        summary: Dict[str, Any],
        account_recommendations: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """AI 투자 가이드 & 매수 추천 브리핑 렌더링 (계좌별 분리 렌더링 및 모바일 탭 인터랙션 지원)"""
        # 1. 다중 계좌 AI 추천 데이터가 있는 경우
        if account_recommendations and len(account_recommendations) > 0:
            total_accounts = len(account_recommendations)

            # 1-1. 다중 계좌인 경우: 상단 탭 필터 바 + 계좌별 AI 가이드 카드들
            if total_accounts > 1:
                tab_buttons = [
                    f'<button class="ai-tab-btn active" onclick="filterAccountAiGuide(\'all\', this)">🌐 전체 ({total_accounts}개 계좌)</button>'
                ]
                account_cards_html = []
                grand_total_rec = 0

                for idx, ar in enumerate(account_recommendations, 1):
                    ar_id = ar.get("account_id", idx)
                    ar_name = ar.get("account_name", f"계좌 {idx}")
                    ar_broker = ar.get("broker", "")
                    d_day = ar.get("d_day")
                    next_buy_date = ar.get("next_buy_date", "")
                    cycle_desc = ar.get("cycle_desc", "정기 투자 주기")
                    already_invested = ar.get("already_invested_this_month", False)
                    total_rec_amt = ar.get("total_recommended_amount", 0)
                    grand_total_rec += total_rec_amt
                    items = ar.get("items", [])

                    custom_comment = ar.get("ai_guide_comment")
                    if custom_comment:
                        guide_comment = custom_comment
                    elif already_invested:
                        guide_comment = f"이번 주기(<strong>{cycle_desc}</strong>) 매수가 성공적으로 완료되었습니다! 포트폴리오 비중이 안정적으로 유지되고 있습니다."
                    elif d_day is not None and d_day == 0:
                        guide_comment = f"오늘은 <strong>정기 매수 실행일(D-Day)</strong>입니다! 오늘 추천된 총 <strong>{total_rec_amt:,.0f}원</strong> 규모의 매수를 진행해 보세요."
                    elif d_day is not None and d_day > 0:
                        guide_comment = f"다음 매수일까지 <strong>{d_day}일</strong> 남았습니다. (예정일: {next_buy_date}) 현재 시장 변동성을 모니터링하며 매수 예산을 준비해 두세요."
                    else:
                        guide_comment = f"설정된 투자 주기에 맞춰 낙폭 과대 종목 및 목표 비중 부족 종목을 우선하여 추천합니다."

                    if already_invested:
                        dday_text = "이번 주기 매수 완료"
                        dday_class = "badge-success"
                    elif d_day is not None and d_day == 0:
                        dday_text = "오늘 매수 D-Day"
                        dday_class = "badge-warning"
                    elif d_day is not None and d_day > 0:
                        dday_text = f"D-{d_day}"
                        dday_class = "badge-info"
                    else:
                        dday_text = "수시 매수"
                        dday_class = "badge-info"

                    tab_buttons.append(
                        f'<button class="ai-tab-btn" onclick="filterAccountAiGuide(\'ai-group-{ar_id}\', this)">🏢 {ar_name}</button>'
                    )

                    # 계좌별 추천 종목 리스트 생성
                    items_html = ""
                    rec_count = 0
                    for it in items:
                        rec_shares = it.get("recommended_shares", 0)
                        if rec_shares > 0:
                            rec_count += 1
                            name = it.get("name", "")
                            ticker = it.get("ticker", "")
                            rec_amount = it.get("recommended_amount", 0)
                            reason = it.get("reason", "비중 확대 추천")
                            items_html += f"""
                            <div class="recom-item-card">
                                <div>
                                    <div class="recom-info-name">{name}</div>
                                    <div class="recom-info-ticker">{ticker} • {reason}</div>
                                </div>
                                <div class="recom-val-box">
                                    <div class="recom-shares">+{rec_shares:,}주</div>
                                    <div class="recom-amt">{rec_amount:,.0f}원</div>
                                </div>
                            </div>
                            """

                    if rec_count == 0:
                        items_html = """
                        <div style="text-align: center; padding: 14px; font-size: 13px; color: var(--text-dim);">
                            현재 즉시 매수를 요하는 비중 불균형 종목이 없습니다. (포트폴리오 균형 양호)
                        </div>
                        """

                    broker_badge = f'<span class="account-broker-label">• {ar_broker}</span>' if ar_broker else ""
                    card_html = f"""
                    <div class="account-ai-group" id="ai-group-{ar_id}">
                        <div class="account-ai-header">
                            <div class="account-group-title">
                                <span class="account-badge-pill">계좌 {idx}</span>
                                <span class="account-name-label">{ar_name}</span>
                                {broker_badge}
                            </div>
                            <span class="badge {dday_class}" style="font-size: 11.5px; padding: 3px 8px;">{dday_text}</span>
                        </div>

                        <div class="ai-guide-box" style="margin-bottom: 12px;">
                            <div class="ai-comment">
                                {guide_comment}
                            </div>
                        </div>

                        <div style="margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-size: 12.5px; font-weight: 700; color: #cbd5e1;">🎯 이번 주기 추천 매수 종목</span>
                            <span style="font-size: 12.5px; font-weight: 700; color: #a5b4fc;">합계 {total_rec_amt:,.0f}원</span>
                        </div>

                        {items_html}
                    </div>
                    """
                    account_cards_html.append(card_html)

                tabs_html = f'<div class="ai-tabs">{"".join(tab_buttons)}</div>'
                all_cards = "\n".join(account_cards_html)

                tab_script = """
                <script>
                function filterAccountAiGuide(targetId, btnElement) {
                    var groups = document.querySelectorAll('.account-ai-group');
                    var btns = document.querySelectorAll('.ai-tab-btn');
                    for (var i = 0; i < btns.length; i++) {
                        btns[i].classList.remove('active');
                    }
                    if (btnElement) {
                        btnElement.classList.add('active');
                    }
                    for (var j = 0; j < groups.length; j++) {
                        if (targetId === 'all' || groups[j].id === targetId) {
                            groups[j].style.display = 'block';
                        } else {
                            groups[j].style.display = 'none';
                        }
                    }
                }
                </script>
                """

                return f"""
                <section class="card">
                    <div class="card-header">
                        <div class="card-title-group">
                            <span class="card-icon">🤖</span>
                            <h2 class="card-title">AI 투자 가이드 & 매수 전략</h2>
                        </div>
                        <span style="font-size: 12px; color: var(--text-dim);">{total_accounts}개 계좌 맞춤 전략</span>
                    </div>
                    {tabs_html}
                    {all_cards}
                    {tab_script}
                </section>
                """

            # 1-2. 단일 계좌인 경우: 깔끔한 계좌 헤더와 단일 AI 가이드
            else:
                ar = account_recommendations[0]
                ar_name = ar.get("account_name", "기본 계좌")
                ar_broker = ar.get("broker", "")
                d_day = ar.get("d_day")
                next_buy_date = ar.get("next_buy_date", "")
                cycle_desc = ar.get("cycle_desc", "정기 투자 주기")
                already_invested = ar.get("already_invested_this_month", False)
                total_rec_amt = ar.get("total_recommended_amount", 0)
                items = ar.get("items", [])

                custom_comment = ar.get("ai_guide_comment")
                if custom_comment:
                    guide_comment = custom_comment
                elif already_invested:
                    guide_comment = f"이번 주기(<strong>{cycle_desc}</strong>) 매수가 성공적으로 완료되었습니다! 포트폴리오 비중이 안정적으로 유지되고 있습니다."
                elif d_day is not None and d_day == 0:
                    guide_comment = f"오늘은 <strong>정기 매수 실행일(D-Day)</strong>입니다! 오늘 추천된 총 <strong>{total_rec_amt:,.0f}원</strong> 규모의 매수를 진행해 보세요."
                elif d_day is not None and d_day > 0:
                    guide_comment = f"다음 매수일까지 <strong>{d_day}일</strong> 남았습니다. (예정일: {next_buy_date}) 현재 시장 변동성을 모니터링하며 매수 예산을 준비해 두세요."
                else:
                    guide_comment = f"설정된 투자 주기에 맞춰 낙폭 과대 종목 및 목표 비중 부족 종목을 우선하여 추천합니다."

                if already_invested:
                    dday_text = "이번 주기 매수 완료"
                    dday_class = "badge-success"
                elif d_day is not None and d_day == 0:
                    dday_text = "오늘 매수 D-Day"
                    dday_class = "badge-warning"
                elif d_day is not None and d_day > 0:
                    dday_text = f"D-{d_day}"
                    dday_class = "badge-info"
                else:
                    dday_text = "수시 매수"
                    dday_class = "badge-info"

                items_html = ""
                rec_count = 0
                for it in items:
                    rec_shares = it.get("recommended_shares", 0)
                    if rec_shares > 0:
                        rec_count += 1
                        name = it.get("name", "")
                        ticker = it.get("ticker", "")
                        rec_amount = it.get("recommended_amount", 0)
                        reason = it.get("reason", "비중 확대 추천")
                        items_html += f"""
                        <div class="recom-item-card">
                            <div>
                                <div class="recom-info-name">{name}</div>
                                <div class="recom-info-ticker">{ticker} • {reason}</div>
                            </div>
                            <div class="recom-val-box">
                                <div class="recom-shares">+{rec_shares:,}주</div>
                                <div class="recom-amt">{rec_amount:,.0f}원</div>
                            </div>
                        </div>
                        """

                if rec_count == 0:
                    items_html = """
                    <div style="text-align: center; padding: 14px; font-size: 13px; color: var(--text-dim);">
                        현재 즉시 매수를 요하는 비중 불균형 종목이 없습니다. (포트폴리오 균형 양호)
                    </div>
                    """

                broker_badge = f'<span class="account-broker-label">• {ar_broker}</span>' if ar_broker else ""
                return f"""
                <section class="card">
                    <div class="card-header">
                        <div class="card-title-group">
                            <span class="card-icon">🤖</span>
                            <h2 class="card-title">AI 투자 가이드 & 매수 전략</h2>
                        </div>
                        <span class="badge {dday_class}">{dday_text}</span>
                    </div>

                    <div class="account-ai-group" style="margin-bottom: 0;">
                        <div class="account-ai-header">
                            <div class="account-group-title">
                                <span class="account-badge-pill">계좌</span>
                                <span class="account-name-label">{ar_name}</span>
                                {broker_badge}
                            </div>
                        </div>

                        <div class="ai-guide-box">
                            <div class="ai-comment">
                                {guide_comment}
                            </div>
                        </div>

                        <div style="margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-size: 13px; font-weight: 700; color: #cbd5e1;">🎯 이번 주기 추천 매수 종목</span>
                            <span style="font-size: 13px; font-weight: 700; color: #a5b4fc;">합계 {total_rec_amt:,.0f}원</span>
                        </div>

                        {items_html}
                    </div>
                </section>
                """

        # 2. 계좌별 추천 데이터가 없는 경우 (기존 호환 및 목 테스트)
        d_day = recommendations.get("d_day", None)
        next_buy_date = recommendations.get("next_buy_date", "")
        cycle_desc = recommendations.get("cycle_desc", "정기 투자 주기")
        already_invested = recommendations.get("already_invested_this_month", False)
        total_rec_amt = recommendations.get("total_recommended_amount", 0)
        items = recommendations.get("items", [])

        if already_invested:
            dday_text = "투자 완료"
            dday_class = "badge-success"
            guide_comment = f"이번 주기(<strong>{cycle_desc}</strong>) 매수가 성공적으로 완료되었습니다! 포트폴리오 비중이 안정적으로 유지되고 있습니다."
        elif d_day is not None and d_day == 0:
            dday_text = "오늘 매수 D-Day"
            dday_class = "badge-warning"
            guide_comment = f"오늘은 <strong>정기 매수 실행일(D-Day)</strong>입니다! 오늘 추천된 총 <strong>{total_rec_amt:,.0f}원</strong> 규모의 매수를 진행해 보세요."
        elif d_day is not None and d_day > 0:
            dday_text = f"D-{d_day}"
            dday_class = "badge-info"
            guide_comment = f"다음 매수일까지 <strong>{d_day}일</strong> 남았습니다. (예정일: {next_buy_date}) 현재 시장 변동성을 모니터링하며 매수 예산을 준비해 두세요."
        else:
            dday_text = "수시 매수"
            dday_class = "badge-info"
            guide_comment = f"설정된 투자 주기에 맞춰 낙폭 과대 종목 및 목표 비중 부족 종목을 우선하여 추천합니다."

        # 추천 종목 리스트 생성
        items_html = ""
        rec_count = 0
        for it in items:
            rec_shares = it.get("recommended_shares", 0)
            if rec_shares > 0:
                rec_count += 1
                name = it.get("name", "")
                ticker = it.get("ticker", "")
                rec_amount = it.get("recommended_amount", 0)
                reason = it.get("reason", "비중 확대 추천")
                items_html += f"""
                <div class="recom-item-card">
                    <div>
                        <div class="recom-info-name">{name}</div>
                        <div class="recom-info-ticker">{ticker} • {reason}</div>
                    </div>
                    <div class="recom-val-box">
                        <div class="recom-shares">+{rec_shares:,}주</div>
                        <div class="recom-amt">{rec_amount:,.0f}원</div>
                    </div>
                </div>
                """

        if rec_count == 0:
            items_html = f"""
            <div style="text-align: center; padding: 14px; font-size: 13px; color: var(--text-dim);">
                현재 즉시 매수를 요하는 비중 불균형 종목이 없습니다. (포트폴리오 균형 양호)
            </div>
            """

        return f"""
        <section class="card">
            <div class="card-header">
                <div class="card-title-group">
                    <span class="card-icon">🤖</span>
                    <h2 class="card-title">AI 투자 가이드 & 매수 전략</h2>
                </div>
                <span class="ai-dday-badge">{dday_text}</span>
            </div>

            <div class="ai-guide-box">
                <div class="ai-comment">
                    {guide_comment}
                </div>
            </div>

            <div style="margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center;">
                <span style="font-size: 13px; font-weight: 700; color: #cbd5e1;">🎯 이번 주기 추천 매수 종목</span>
                <span style="font-size: 13px; font-weight: 700; color: #a5b4fc;">합계 {total_rec_amt:,.0f}원</span>
            </div>

            {items_html}
        </section>
        """

    def _render_positions_section(
        self,
        positions: List[Dict[str, Any]],
        account_groups: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """등록 및 보유 종목별 세부 현황 렌더링 (계좌별 분리 렌더링 및 모바일 탭 인터랙션 지원)"""
        # 1. 계좌별 그룹 데이터가 있는 경우
        if account_groups and len(account_groups) > 0:
            total_stocks = sum(len(ag.get("positions", [])) for ag in account_groups)
            total_accounts = len(account_groups)

            # 1-1. 다중 계좌인 경우: 상단 탭 필터 바 + 계좌별 그룹 카드들
            if total_accounts > 1:
                tab_buttons = [
                    f'<button class="account-tab-btn active" onclick="filterAccountPositions(\'all\', this)">🌐 전체 ({total_stocks}개)</button>'
                ]
                account_cards_html = []

                for idx, ag in enumerate(account_groups, 1):
                    ag_id = ag.get("account_id", idx)
                    ag_name = ag.get("account_name", f"계좌 {idx}")
                    ag_broker = ag.get("broker", "")
                    ag_eval = ag.get("total_eval", 0.0)
                    ag_cost = ag.get("total_cost", 0.0)
                    ag_pl = ag.get("total_pl", 0.0)
                    ag_pl_pct = ag.get("total_pl_pct", 0.0)
                    ag_cash = ag.get("cash_balance", 0.0)
                    ag_pos = ag.get("positions", [])

                    ag_sign = "+" if ag_pl > 0 else ""
                    ag_badge_cls = "badge-success" if ag_pl >= 0 else "badge-danger"

                    tab_buttons.append(
                        f'<button class="account-tab-btn" onclick="filterAccountPositions(\'acc-group-{ag_id}\', this)">🏢 {ag_name} ({len(ag_pos)}개)</button>'
                    )

                    items_html = self._render_position_rows(ag_pos)
                    if not items_html:
                        items_html = """
                        <div style="text-align: center; padding: 14px; font-size: 12px; color: var(--text-dim);">
                            등록된 목표 종목 또는 보유 내역이 없습니다.
                        </div>
                        """

                    broker_badge = f'<span class="account-broker-label">• {ag_broker}</span>' if ag_broker else ""
                    card_html = f"""
                    <div class="account-pos-group" id="acc-group-{ag_id}">
                        <div class="account-pos-header">
                            <div class="account-group-title">
                                <span class="account-badge-pill">계좌 {idx}</span>
                                <span class="account-name-label">{ag_name}</span>
                                {broker_badge}
                            </div>
                            <div class="account-group-kpi">
                                <span class="account-eval-amount">{ag_eval:,.0f}원</span>
                                <span class="badge {ag_badge_cls}">{ag_sign}{ag_pl_pct:.2f}%</span>
                            </div>
                        </div>
                        <div class="account-sub-meta">
                            <span>원금 {ag_cost:,.0f}원</span>
                            <span>•</span>
                            <span>예수금 {ag_cash:,.0f}원</span>
                            <span>•</span>
                            <span>종목 {len(ag_pos)}개</span>
                        </div>
                        <div>
                            {items_html}
                        </div>
                    </div>
                    """
                    account_cards_html.append(card_html)

                tabs_html = f'<div class="account-tabs">{"".join(tab_buttons)}</div>'
                all_cards = "\n".join(account_cards_html)

                tab_script = """
                <script>
                function filterAccountPositions(targetId, btnElement) {
                    var groups = document.querySelectorAll('.account-pos-group');
                    var btns = document.querySelectorAll('.account-tab-btn');
                    for (var i = 0; i < btns.length; i++) {
                        btns[i].classList.remove('active');
                    }
                    if (btnElement) {
                        btnElement.classList.add('active');
                    }
                    for (var j = 0; j < groups.length; j++) {
                        if (targetId === 'all' || groups[j].id === targetId) {
                            groups[j].style.display = 'block';
                        } else {
                            groups[j].style.display = 'none';
                        }
                    }
                }
                </script>
                """

                return f"""
                <section class="card">
                    <div class="card-header">
                        <div class="card-title-group">
                            <span class="card-icon">📊</span>
                            <h2 class="card-title">등록 및 보유 종목 세부 현황</h2>
                        </div>
                        <span style="font-size: 12px; color: var(--text-dim);">{total_accounts}개 계좌 · {total_stocks}개 종목</span>
                    </div>
                    {tabs_html}
                    {all_cards}
                    {tab_script}
                </section>
                """

            # 1-2. 단일 계좌인 경우: 깔끔한 계좌 헤더와 종목 리스트
            else:
                ag = account_groups[0]
                ag_name = ag.get("account_name", "기본 계좌")
                ag_broker = ag.get("broker", "")
                ag_eval = ag.get("total_eval", 0.0)
                ag_cost = ag.get("total_cost", 0.0)
                ag_pl = ag.get("total_pl", 0.0)
                ag_pl_pct = ag.get("total_pl_pct", 0.0)
                ag_cash = ag.get("cash_balance", 0.0)
                ag_pos = ag.get("positions", [])
                ag_sign = "+" if ag_pl > 0 else ""
                ag_badge_cls = "badge-success" if ag_pl >= 0 else "badge-danger"

                broker_badge = f'<span class="account-broker-label">• {ag_broker}</span>' if ag_broker else ""
                items_html = self._render_position_rows(ag_pos)

                return f"""
                <section class="card">
                    <div class="card-header">
                        <div class="card-title-group">
                            <span class="card-icon">📊</span>
                            <h2 class="card-title">등록 및 보유 종목 세부 현황</h2>
                        </div>
                        <span style="font-size: 12px; color: var(--text-dim);">{len(ag_pos)}개 종목</span>
                    </div>
                    <div class="account-pos-group" style="margin-bottom: 0;">
                        <div class="account-pos-header">
                            <div class="account-group-title">
                                <span class="account-badge-pill">계좌</span>
                                <span class="account-name-label">{ag_name}</span>
                                {broker_badge}
                            </div>
                            <div class="account-group-kpi">
                                <span class="account-eval-amount">{ag_eval:,.0f}원</span>
                                <span class="badge {ag_badge_cls}">{ag_sign}{ag_pl_pct:.2f}%</span>
                            </div>
                        </div>
                        <div class="account-sub-meta">
                            <span>원금 {ag_cost:,.0f}원</span>
                            <span>•</span>
                            <span>예수금 {ag_cash:,.0f}원</span>
                        </div>
                        <div>
                            {items_html}
                        </div>
                    </div>
                </section>
                """

        # 2. 계좌 그룹이 없는 경우 (기존 호환 및 Mock 테스트)
        if not positions:
            return ""

        rows_html = self._render_position_rows(positions)
        return f"""
        <section class="card">
            <div class="card-header">
                <div class="card-title-group">
                    <span class="card-icon">📊</span>
                    <h2 class="card-title">등록 및 보유 종목 세부 현황</h2>
                </div>
                <span style="font-size: 12px; color: var(--text-dim);">{len(positions)}개 종목</span>
            </div>
            {rows_html}
        </section>
        """

    def _render_position_rows(self, positions: List[Dict[str, Any]]) -> str:
        """종목 리스트 HTML 행 렌더링 헬퍼"""
        rows_html = ""
        for p in positions:
            name = p.get("name", "")
            ticker = p.get("ticker", "")
            eval_amount = p.get("eval_amount", 0)
            pl_pct = p.get("pl_pct", 0.0)
            shares = p.get("shares", 0)
            current_price = p.get("current_price", 0)
            cur_weight = p.get("current_weight", 0.0) * 100
            target_weight = p.get("target_weight", 0.0) * 100

            pl_class = "pl-plus" if pl_pct > 0 else ("pl-minus" if pl_pct < 0 else "pl-zero")
            pl_sign = "+" if pl_pct > 0 else ""
            progress_width = min(cur_weight, 100.0)

            if shares > 0:
                detail_html = f"""
                <div class="pos-details">
                    <span>{shares:,}주 × {current_price:,.0f}원</span>
                    <span class="{pl_class}">{pl_sign}{pl_pct:.2f}%</span>
                </div>
                """
            else:
                detail_html = f"""
                <div class="pos-details">
                    <span style="color: var(--text-dim);">미보유 (현재가: {current_price:,.0f}원)</span>
                    <span style="color: #94a3b8; font-size: 11px;">신규 편입 대기</span>
                </div>
                """

            rows_html += f"""
            <div class="pos-item">
                <div class="pos-header">
                    <span class="pos-name">{name} <span style="font-size: 11px; color: var(--text-dim); font-weight: normal;">({ticker})</span></span>
                    <span class="pos-eval">{eval_amount:,.0f}원</span>
                </div>
                {detail_html}
                <div style="display: flex; justify-content: space-between; font-size: 11px; color: var(--text-dim); margin-top: 6px;">
                    <span>현재비중: {cur_weight:.1f}%</span>
                    <span>목표비중: {target_weight:.1f}%</span>
                </div>
                <div class="progress-bar-bg">
                    <div class="progress-bar-fill" style="width: {progress_width:.1f}%;"></div>
                </div>
            </div>
            """
        return rows_html

    def _render_news_section(self, news_items: List[Dict[str, Any]]) -> str:
        """관심/보유 종목 맞춤 뉴스 브리핑 렌더링"""
        if not news_items:
            return ""

        items_html = ""
        for n in news_items[:8]:  # 최대 8건
            title = n.get("title", "")
            media = n.get("media", "언론사")
            date_time = n.get("date", "")
            link = n.get("link", "#")
            tag = n.get("tag", "증시")

            items_html += f"""
            <div class="news-item">
                <div class="news-tag-box">
                    <span class="news-tag">{tag}</span>
                    <span class="news-media">{media}</span>
                </div>
                <a href="{link}" target="_blank" class="news-title">{title}</a>
                <span class="news-time">{date_time}</span>
            </div>
            """

        return f"""
        <section class="card">
            <div class="card-header">
                <div class="card-title-group">
                    <span class="card-icon">📰</span>
                    <h2 class="card-title">맞춤 시황 & 관심종목 뉴스</h2>
                </div>
                <span class="badge badge-info">실시간 픽</span>
            </div>
            {items_html}
        </section>
        """

    def _render_macro_dashboard_section(self, macro_data: Dict[str, Any]) -> str:
        """글로벌 10대 지표 및 5일 트렌드 대시보드 렌더링"""
        raw = macro_data.get("raw_items", {})
        fund = macro_data.get("fundamentals", {})
        if not raw and not fund:
            return ""

        def _card(k: str) -> str:
            item = raw.get(k, {})
            name = item.get("name", k)
            sym = item.get("symbol", "")
            price_str = item.get("price_str", "-")
            change_pct = item.get("change_pct", 0.0)
            change_str = item.get("change_str", "-")
            trend = item.get("trend", "FLAT")
            badge = item.get("trend_badge", "━ 보합")

            chg_class = "pl-plus" if change_pct > 0 else ("pl-minus" if change_pct < 0 else "pl-zero")
            badge_class = "trend-badge-up" if trend == "UP" else ("trend-badge-down" if trend == "DOWN" else "trend-badge-flat")

            return f"""
            <div class="macro-card">
                <div class="macro-card-name" title="{name} ({sym})">{name}</div>
                <div class="macro-card-val">{price_str}</div>
                <div class="macro-card-footer">
                    <span style="font-size: 10.5px; font-weight: 700;" class="{chg_class}">전일 {change_str}</span>
                    <span class="trend-badge {badge_class}">{badge}</span>
                </div>
            </div>
            """

        def _fund_row(k: str) -> str:
            item = fund.get(k, {})
            name = item.get("name", k)
            val = item.get("latest_value", "-")
            trend = item.get("trend", "FLAT")
            badge = item.get("trend_badge", "-")
            desc = item.get("description", "")
            period = item.get("period", "")

            badge_class = "trend-badge-up" if trend == "UP" else ("trend-badge-down" if trend == "DOWN" else "trend-badge-flat")

            return f"""
            <div class="macro-fund-item">
                <div class="macro-fund-info">
                    <div class="macro-fund-name">{name} <span style="font-size: 10px; color: var(--text-dim); font-weight: normal;">({period})</span></div>
                    <div class="macro-fund-desc">{desc}</div>
                </div>
                <div class="macro-fund-valbox">
                    <div class="macro-fund-val">{val}</div>
                    <span class="trend-badge {badge_class}">{badge}</span>
                </div>
            </div>
            """

        return f"""
        <section class="card" style="border: 1px solid rgba(56, 189, 248, 0.35); margin-bottom: 18px;">
            <div class="card-header">
                <div class="card-title-group">
                    <span class="card-icon">🌐</span>
                    <h2 class="card-title">글로벌 10대 지표 & 최근 트렌드</h2>
                </div>
                <span class="badge badge-info">5일 모멘텀 & 펀더멘털</span>
            </div>

            <!-- 1. 미국 3대 증시 -->
            <div class="macro-subgroup">
                <div class="macro-group-title">
                    <span>🇺🇸</span> <span>미국 3대 증시 (S&P 500 · 나스닥 100 · 다우존스)</span>
                </div>
                <div class="macro-grid-3">
                    {_card("sp500")}
                    {_card("nasdaq100")}
                    {_card("dow")}
                </div>
            </div>

            <!-- 2. 국내 2대 증시 -->
            <div class="macro-subgroup">
                <div class="macro-group-title">
                    <span>🇰🇷</span> <span>국내 2대 증시 (코스피 · 코스닥)</span>
                </div>
                <div class="macro-grid-2">
                    {_card("kospi")}
                    {_card("kosdaq")}
                </div>
            </div>

            <!-- 3. 핵심 거시 지표 -->
            <div class="macro-subgroup">
                <div class="macro-group-title">
                    <span>⚡</span> <span>핵심 거시 지표 (환율 · 원자재 · 금리)</span>
                </div>
                <div class="macro-grid-3">
                    {_card("usd_krw")}
                    {_card("wti_oil")}
                    {_card("us10y_yield")}
                </div>
            </div>

            <!-- 4. 미국 펀더멘털 -->
            <div class="macro-subgroup" style="margin-bottom: 0;">
                <div class="macro-group-title">
                    <span>🏦</span> <span>미국 주요 경제 펀더멘털 (물가 & 고용)</span>
                </div>
                <div style="display: flex; flex-direction: column; gap: 6px;">
                    {_fund_row("core_pce")}
                    {_fund_row("jobs_nfp")}
                    {_fund_row("unemployment_rate")}
                </div>
            </div>
        </section>
        """

    def _render_market_section(self, market_indices: Dict[str, Any]) -> str:
        """주요 시장 지수 요약 렌더링"""
        if not market_indices:
            return ""

        items_html = ""
        for name, data in market_indices.items():
            val = data.get("price", "-")
            chg_pct = data.get("change_pct", 0.0)
            chg_class = "pl-plus" if chg_pct > 0 else ("pl-minus" if chg_pct < 0 else "pl-zero")
            sign = "+" if chg_pct > 0 else ""

            items_html += f"""
            <div class="market-item">
                <div class="market-name">{name}</div>
                <div class="market-val">{val}</div>
                <div class="market-change {chg_class}">{sign}{chg_pct:.2f}%</div>
            </div>
            """

        return f"""
        <div class="market-grid" style="margin-bottom: 18px;">
            {items_html}
        </div>
        """

    @staticmethod
    def _clean_display_text(text: str) -> str:
        """HTML 표출 시 JSON 문법 기호나 코드블록이 전혀 노출되지 않도록 최종 정제"""
        if not text:
            return ""
        t = str(text).strip()
        for fence in ["```json", "```JSON", "'''json", "'''JSON", "```", "'''"]:
            t = t.replace(fence, "")
        t = re.sub(r'["\']?(?:one_line[_\"]?summary|macro_analysis|strategy_advice)["\']?\s*:\s*', '', t, flags=re.IGNORECASE)
        t = t.replace("{", "").replace("}", "").strip()
        lines = [line.strip().strip('",\'') for line in t.splitlines() if line.strip().strip('",\'')]
        return "\n".join(lines).strip()

    def _render_gemini_section(self, gemini_analysis: Dict[str, Any]) -> str:
        """Google Gemini AI 매크로 투자 가이드 섹션 렌더링"""
        if not gemini_analysis or not gemini_analysis.get("success"):
            return ""

        model_name = gemini_analysis.get("model_used", "gemini-3.8-flash")
        model_display = model_name.upper().replace("-", " ")
        stance_badge = gemini_analysis.get("stance_badge", "")
        one_line = self._clean_display_text(gemini_analysis.get("one_line_summary", ""))
        macro_text = self._clean_display_text(gemini_analysis.get("macro_analysis", "")).replace("\n", "<br>")
        strategy_text = self._clean_display_text(gemini_analysis.get("strategy_advice", "")).replace("\n", "<br>")
        usd_krw = gemini_analysis.get("usd_krw", "").strip()

        usd_tag_html = f'<span class="gemini-tag">USD/KRW {usd_krw}</span>' if usd_krw else ""
        stance_badge_html = f'<span class="badge" style="background: rgba(192, 132, 252, 0.25); color: #f3e8ff; border: 1px solid rgba(192, 132, 252, 0.5); font-weight: 700;">{stance_badge}</span>' if stance_badge else ""

        return f"""
        <section class="card" style="border: 1px solid rgba(168, 85, 247, 0.35);">
            <div class="card-header">
                <div class="card-title-group">
                    <span class="card-icon">✨</span>
                    <h2 class="card-title">Gemini AI 매크로 투자 가이드</h2>
                </div>
                <div style="display: flex; gap: 6px; align-items: center;">
                    {stance_badge_html}
                    <span class="badge" style="background: rgba(168, 85, 247, 0.2); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.4);">
                        {model_display}
                    </span>
                </div>
            </div>

            <div class="gemini-quote-box">
                <div class="gemini-quote-text">
                    "{one_line}"
                </div>
            </div>

            <div class="gemini-block">
                <div class="gemini-block-title">
                    <span>🌍 글로벌 매크로 & 시황 분석</span>
                    {usd_tag_html}
                </div>
                <div class="gemini-block-content">
                    {macro_text}
                </div>
            </div>

            <div class="gemini-block" style="margin-bottom: 0;">
                <div class="gemini-block-title" style="color: #c084fc;">
                    <span>🎯 포트폴리오 맞춤 분할매수 전략</span>
                </div>
                <div class="gemini-block-content">
                    {strategy_text}
                </div>
            </div>
        </section>
        """

