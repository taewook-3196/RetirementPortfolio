"""
services/news_service.py
하이브리드 뉴스 수집 서비스 (네이버 증권 모바일 API + 구글 뉴스 RSS).
- 사용자 등록 ETF 및 관심종목 관련 뉴스 수집 (네이버 금융)
- ETF 핵심 편입 구성종목(엔비디아, 애플, 마이크로소프트, 테슬라, 삼성전자 등) 키워드 뉴스 수집 (구글 RSS)
- 거시경제 / 증시 최신 속보 수집 (구글 뉴스 비즈니스 RSS)
- '내 종목만 보기' 및 '전체 경제 뉴스 보기' 필터링 지원
"""

from __future__ import annotations
import logging
import urllib.request
import urllib.parse
import ssl
import json
import re
import html
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional

logger = logging.getLogger("RetirementPortfolio.NewsService")

# ETF별 대표 편입 구성종목 및 핵심 테마 키워드 매핑
ETF_CONSTITUENTS_MAP: Dict[str, Dict[str, Any]] = {
    "381170": {
        "tag": "미국빅테크",
        "query": "엔비디아 OR 애플 OR 마이크로소프트 OR 테슬라 OR 알파벳",
        "keywords": ["엔비디아", "애플", "마이크로소프트", "테슬라", "빅테크"],
    },
    "488500": {
        "tag": "S&P500",
        "query": "S&P500 OR 뉴욕증시 OR 미국 증시",
        "keywords": ["S&P500", "뉴욕증시", "미국증시"],
    },
    "442560": {
        "tag": "자산배분·TDF",
        "query": "퇴직연금 OR TDF OR 디폴트옵션 OR 글로벌 자산배분",
        "keywords": ["퇴직연금", "TDF", "자산배분"],
    },
    "069500": {
        "tag": "코스피 대형주",
        "query": "삼성전자 OR SK하이닉스 OR 코스피",
        "keywords": ["삼성전자", "SK하이닉스", "코스피"],
    },
}


class NewsService:
    """금융 뉴스 수집 및 피드 가공 서비스"""

    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    def __init__(self):
        # SSL 인증서 검증 컨텍스트
        self.ssl_context = ssl._create_unverified_context()

    def fetch_stock_news(self, ticker: str, stock_name: str = "") -> List[Dict[str, Any]]:
        """네이버 모바일 금융 API를 통해 종목코드 기반 뉴스를 수집합니다."""
        clean_ticker = str(ticker).strip()
        url = f"https://m.stock.naver.com/api/news/stock/{clean_ticker}?pageSize=8&page=1"
        req = urllib.request.Request(url, headers={"User-Agent": self.USER_AGENT})

        results: List[Dict[str, Any]] = []
        try:
            with urllib.request.urlopen(req, context=self.ssl_context, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                
                # m.stock.naver.com은 [{'total': 1, 'items': [...]}] 형식
                item_lists = []
                if isinstance(data, list):
                    for entry in data:
                        if isinstance(entry, dict) and "items" in entry:
                            item_lists.extend(entry.get("items", []))
                        elif isinstance(entry, dict) and "title" in entry:
                            item_lists.append(entry)
                elif isinstance(data, dict):
                    item_lists = data.get("items", []) or data.get("content", [])

                for it in item_lists:
                    raw_title = it.get("titleFull") or it.get("title", "")
                    clean_title = html.unescape(re.sub(r"<[^>]+>", "", raw_title).strip())
                    if not clean_title:
                        continue

                    link = it.get("mobileNewsUrl", "") or f"https://finance.naver.com/item/news_read.naver?article_id={it.get('articleId')}&office_id={it.get('officeId')}&code={clean_ticker}"
                    results.append({
                        "tag": stock_name or clean_ticker,
                        "title": clean_title,
                        "press": it.get("officeName", "네이버금융"),
                        "datetime": it.get("datetime", ""),
                        "link": link,
                        "category": "stock",
                    })
        except Exception as e:
            logger.warning("종목 뉴스 수집 실패 (%s): %s", clean_ticker, e)

        return results

    def fetch_economy_rss(self, limit: int = 15) -> List[Dict[str, Any]]:
        """구글 뉴스 비즈니스/경제 RSS를 통해 주요 실시간 경제 속보를 수집합니다."""
        url = "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko"
        req = urllib.request.Request(url, headers={"User-Agent": self.USER_AGENT})

        results: List[Dict[str, Any]] = []
        try:
            with urllib.request.urlopen(req, context=self.ssl_context, timeout=6) as resp:
                root = ET.fromstring(resp.read())
                items = root.findall(".//item")
                for it in items[:limit]:
                    title_elem = it.find("title")
                    link_elem = it.find("link")
                    source_elem = it.find("source")
                    date_elem = it.find("pubDate")

                    if title_elem is None or not title_elem.text:
                        continue

                    raw_title = title_elem.text
                    source_name = source_elem.text if (source_elem is not None and source_elem.text) else "경제속보"
                    # "제목 - 언론사" 형태 분리
                    if " - " in raw_title:
                        parts = raw_title.rsplit(" - ", 1)
                        clean_title = parts[0].strip()
                        if not source_name or source_name == "경제속보":
                            source_name = parts[1].strip()
                    else:
                        clean_title = raw_title.strip()

                    link = link_elem.text if link_elem is not None else ""
                    wdate = date_elem.text if date_elem is not None else ""

                    results.append({
                        "tag": "경제속보",
                        "title": clean_title,
                        "press": source_name,
                        "datetime": wdate,
                        "link": link,
                        "category": "economy",
                    })
        except Exception as e:
            logger.warning("구글 경제 RSS 수집 실패: %s", e)

        return results

    def fetch_keyword_rss(self, keyword_query: str, tag: str, limit: int = 6) -> List[Dict[str, Any]]:
        """구글 뉴스 키워드 검색 RSS를 통해 ETF 핵심 편입종목 뉴스를 수집합니다."""
        encoded_query = urllib.parse.quote(keyword_query)
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko"
        req = urllib.request.Request(url, headers={"User-Agent": self.USER_AGENT})

        results: List[Dict[str, Any]] = []
        try:
            with urllib.request.urlopen(req, context=self.ssl_context, timeout=6) as resp:
                root = ET.fromstring(resp.read())
                items = root.findall(".//item")
                for it in items[:limit]:
                    title_elem = it.find("title")
                    link_elem = it.find("link")
                    source_elem = it.find("source")
                    date_elem = it.find("pubDate")

                    if title_elem is None or not title_elem.text:
                        continue

                    raw_title = title_elem.text
                    source_name = source_elem.text if (source_elem is not None and source_elem.text) else "금융뉴스"
                    if " - " in raw_title:
                        parts = raw_title.rsplit(" - ", 1)
                        clean_title = parts[0].strip()
                        if not source_name or source_name == "금융뉴스":
                            source_name = parts[1].strip()
                    else:
                        clean_title = raw_title.strip()

                    link = link_elem.text if link_elem is not None else ""
                    wdate = date_elem.text if date_elem is not None else ""

                    results.append({
                        "tag": tag,
                        "title": clean_title,
                        "press": source_name,
                        "datetime": wdate,
                        "link": link,
                        "category": "constituent",
                    })
        except Exception as e:
            logger.warning("키워드 RSS 수집 실패 (%s): %s", tag, e)

        return results

    def get_constituent_query(self, ticker: str, name: str = "") -> Optional[tuple[str, str]]:
        """종목코드 및 종목명 기반으로 핵심 편입종목/테마 쿼리 및 태그를 추출합니다."""
        clean_ticker = str(ticker).strip()
        if clean_ticker in ETF_CONSTITUENTS_MAP:
            m = ETF_CONSTITUENTS_MAP[clean_ticker]
            return m["query"], m["tag"]

        n = name or ""
        if any(k in n for k in ["반도체", "SOX", "필라델피아"]):
            return "엔비디아 OR TSMC OR SK하이닉스 OR 반도체", "반도체"
        if any(k in n for k in ["배당", "다우존스", "SCHD", "인컴"]):
            return "미국배당다우존스 OR 배당성장 OR 슈드", "배당·인컴"
        if any(k in n for k in ["2차전지", "배터리"]):
            return "2차전지 OR LG에너지솔루션 OR 에코프로", "2차전지"
        if any(k in n for k in ["바이오", "헬스케어", "제약"]):
            return "바이오 OR 일라이릴리 OR 셀트리온", "바이오·헬스"
        if any(k in n for k in ["AI", "인공지능", "로봇"]):
            return "인공지능 OR AI OR 로봇 OR 오픈AI", "AI·로봇"
        if any(k in n for k in ["나스닥", "빅테크", "테크"]):
            return "나스닥 OR 엔비디아 OR 애플 OR 마이크로소프트", "빅테크"
        if any(k in n for k in ["채권", "국채", "금리"]):
            return "미국국채 OR 국채금리 OR 연준", "채권·금리"
        if any(k in n for k in ["방산", "우주", "항공"]):
            return "K방산 OR 한화에어로스페이스 OR 우주항공", "방산·우주"
        if any(k in n for k in ["원전", "원자력", "전력"]):
            return "원전 OR 원자력 OR 소형원자로", "원전·전력"
        if any(k in n for k in ["코스피", "200"]):
            return "삼성전자 OR SK하이닉스 OR 코스피", "코스피 대형주"
        if any(k in n for k in ["TDF", "퇴직연금"]):
            return "퇴직연금 OR TDF OR 자산배분", "자산배분·TDF"

        # 일반 개별 종목인 경우 해당 종목명을 직접 검색
        clean_name = re.sub(r"^(KODEX|TIGER|ACE|SOL|RISE|KBSTAR|ARIRANG|PLUS)\s*", "", n).strip()
        if clean_name and len(clean_name) >= 2:
            return clean_name, clean_name[:8]

        return None

    def get_news_feed(
        self,
        mode: str = "all",
        etfs: Optional[List[Any]] = None,
        watchlist: Optional[List[Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        설정된 모드('all' 또는 'portfolio_only')에 따라 뉴스를 수집하고 취합하여 반환합니다.
        - mode == 'portfolio_only': 내 ETF 종목 + 관심종목 + 핵심 구성종목 뉴스만 포함
        - mode == 'all': 위 종목 뉴스 + 최신 거시경제/증시 속보 종합 포함
        """
        etf_list = etfs or []
        watch_list = watchlist or []

        collected_stock_news: List[Dict[str, Any]] = []
        collected_constituent_news: List[Dict[str, Any]] = []

        # 1. 내 ETF 종목별 뉴스 및 핵심 구성종목 뉴스 수집
        for etf in etf_list:
            ticker = getattr(etf, "ticker", "")
            name = getattr(etf, "name", "")
            if not ticker:
                continue

            # (1) ETF 자체 종목 뉴스
            stock_items = self.fetch_stock_news(ticker, name)
            collected_stock_news.extend(stock_items)

            # (2) ETF 핵심 편입종목 뉴스 (예: 381170 -> 엔비디아, 애플 등 또는 지능형 테마 검색)
            const_info = self.get_constituent_query(ticker, name)
            if const_info:
                c_query, c_tag = const_info
                const_items = self.fetch_keyword_rss(c_query, tag=c_tag, limit=4)
                collected_constituent_news.extend(const_items)

        # 2. 관심종목(Watchlist) 뉴스 수집
        for w in watch_list:
            ticker = getattr(w, "ticker", "")
            name = getattr(w, "name", "")
            if not ticker:
                continue
            stock_items = self.fetch_stock_news(ticker, name)
            collected_stock_news.extend(stock_items)

            const_info = self.get_constituent_query(ticker, name)
            if const_info:
                c_query, c_tag = const_info
                const_items = self.fetch_keyword_rss(c_query, tag=c_tag, limit=4)
                collected_constituent_news.extend(const_items)

        # 3. 전체 경제 뉴스 수집 (mode == 'all'인 경우)
        collected_economy_news: List[Dict[str, Any]] = []
        if mode == "all":
            collected_economy_news = self.fetch_economy_rss(limit=15)

        # 4. 피드 병합 및 중복 제거 (제목 앞 20글자 기준 유사 중복 방지)
        seen_titles = set()
        final_feed: List[Dict[str, Any]] = []

        def add_unique(items: List[Dict[str, Any]]):
            for it in items:
                norm_title = re.sub(r"[\s\W_]+", "", it.get("title", ""))[:25]
                if norm_title and norm_title not in seen_titles:
                    seen_titles.add(norm_title)
                    final_feed.append(it)

        # 피드가 단조롭지 않도록 종목 뉴스 -> 구성종목 뉴스 -> 경제 속보를 교차 배치
        max_len = max(len(collected_stock_news), len(collected_constituent_news), len(collected_economy_news), 1)
        for i in range(max_len):
            if i < len(collected_stock_news):
                add_unique([collected_stock_news[i]])
            if i < len(collected_constituent_news):
                add_unique([collected_constituent_news[i]])
            if i < len(collected_economy_news):
                add_unique([collected_economy_news[i]])

        # 5. 폴백 (네트워크 미연결 등으로 비어있을 경우 대비)
        if not final_feed:
            final_feed = [
                {
                    "tag": "금융속보",
                    "title": "퇴직연금 ETF 포트폴리오를 통한 기계적 분할 매수로 장기 복리 수익을 추구하세요.",
                    "press": "자산관리시스템",
                    "datetime": "",
                    "link": "https://finance.naver.com",
                    "category": "info",
                },
                {
                    "tag": "미국빅테크",
                    "title": "글로벌 AI 반도체 및 주요 빅테크 기업들의 실적과 성장 모멘텀이 이어지고 있습니다.",
                    "press": "글로벌증시",
                    "datetime": "",
                    "link": "https://finance.naver.com",
                    "category": "info",
                },
            ]

        logger.info("뉴스 피드 생성 완료 (모드: %s, 총 %d건)", mode, len(final_feed))
        return final_feed
