"""
strategy/cycle_helper.py
개인별/계좌별 매수 투자 주기 및 다음 매수 예정일(D-day) 계산 유틸리티.
- 주기 구분: none(없음), daily(매일), weekly(매주), biweekly(격주), monthly(매월), bimonthly(격월), quarterly(분기)
- 다음 예정일 및 D-day, 설명 텍스트 반환
"""

from __future__ import annotations
from datetime import date, datetime, timedelta
import calendar
from typing import Optional, Tuple

WEEKDAYS_KR = {
    "MON": ("월요일", 0),
    "TUE": ("화요일", 1),
    "WED": ("수요일", 2),
    "THU": ("목요일", 3),
    "FRI": ("금요일", 4),
    "SAT": ("토요일", 5),
    "SUN": ("일요일", 6),
}

WEEKDAY_NAMES_MAP = {
    0: "월요일",
    1: "화요일",
    2: "수요일",
    3: "목요일",
    4: "금요일",
    5: "토요일",
    6: "일요일",
}


def format_cycle_description(cycle_type: str, cycle_detail: str) -> str:
    """주기 유형과 세부 설정에 대한 한글 친화적 설명 반환"""
    ctype = (cycle_type or "none").lower()
    cdetail = (cycle_detail or "").strip().upper()

    if ctype == "none":
        return "수동 매수 (주기 없음)"
    elif ctype == "daily":
        return "매일 (영업일 매수)"
    elif ctype == "weekly":
        day_kr = WEEKDAYS_KR.get(cdetail, ("지정 요일", 0))[0]
        return f"매주 {day_kr}"
    elif ctype == "biweekly":
        day_kr = WEEKDAYS_KR.get(cdetail, ("지정 요일", 4))[0]
        return f"격주 {day_kr}"
    elif ctype == "monthly":
        if cdetail == "LAST":
            return "매월 말일"
        day_num = cdetail if cdetail.isdigit() else "25"
        return f"매월 {day_num}일"
    elif ctype == "bimonthly":
        if cdetail == "LAST":
            return "격월 말일"
        day_num = cdetail if cdetail.isdigit() else "25"
        return f"격월 {day_num}일"
    elif ctype == "quarterly":
        if cdetail == "LAST":
            return "분기 말일"
        day_num = cdetail if cdetail.isdigit() else "25"
        return f"분기별 {day_num}일 (1/4/7/10월)"
    return "매월 25일"


def calculate_next_investment_date(
    cycle_type: str,
    cycle_detail: str,
    base_date: Optional[date] = None,
) -> Tuple[Optional[date], Optional[int], str]:
    """
    주기 유형 및 세부 설정을 바탕으로 다음 매수 예정일, 남은 일수(D-day), 요약 텍스트를 산출합니다.
    반환: (next_date, days_remaining, display_str)
    - days_remaining: 0이면 오늘 매수일, 양수면 D-N, 음수는 없음
    """
    today = base_date or date.today()
    ctype = (cycle_type or "none").lower()
    cdetail = (cycle_detail or "").strip().upper()
    desc = format_cycle_description(ctype, cdetail)

    if ctype == "none":
        return None, None, f"{desc} | 계획에 따라 자유 매수"

    if ctype == "daily":
        # 오늘이 평일이면 오늘, 주말이면 다음주 월요일
        if today.weekday() < 5:
            target = today
        else:
            days_ahead = (7 - today.weekday()) % 7
            target = today + timedelta(days=days_ahead)
        diff = (target - today).days
        status_text = "오늘 매수일" if diff == 0 else f"D-{diff} ({target.strftime('%m-%d')} 월)"
        return target, diff, f"{desc} | {status_text}"

    if ctype == "weekly":
        target_weekday = WEEKDAYS_KR.get(cdetail, ("화요일", 1))[1]
        days_ahead = (target_weekday - today.weekday()) % 7
        target = today + timedelta(days=days_ahead)
        diff = (target - today).days
        day_name = WEEKDAY_NAMES_MAP.get(target.weekday(), "")
        status_text = "오늘 매수일" if diff == 0 else f"D-{diff} ({target.strftime('%m-%d')} {day_name})"
        return target, diff, f"{desc} | {status_text}"

    if ctype == "biweekly":
        target_weekday = WEEKDAYS_KR.get(cdetail, ("금요일", 4))[1]
        days_ahead = (target_weekday - today.weekday()) % 7
        target = today + timedelta(days=days_ahead)
        diff = (target - today).days
        day_name = WEEKDAY_NAMES_MAP.get(target.weekday(), "")
        status_text = "오늘 매수일" if diff == 0 else f"D-{diff} ({target.strftime('%m-%d')} {day_name})"
        return target, diff, f"{desc} | {status_text}"

    if ctype == "monthly":
        # 매월 특정 일 또는 말일
        cur_year = today.year
        cur_month = today.month

        def get_monthly_target(y: int, m: int) -> date:
            _, max_day = calendar.monthrange(y, m)
            if cdetail == "LAST":
                day = max_day
            else:
                day = min(int(cdetail) if cdetail.isdigit() else 25, max_day)
            return date(y, m, day)

        target = get_monthly_target(cur_year, cur_month)
        if target < today:
            # 이번 달 날짜가 지났으면 다음 달로
            if cur_month == 12:
                target = get_monthly_target(cur_year + 1, 1)
            else:
                target = get_monthly_target(cur_year, cur_month + 1)

        diff = (target - today).days
        day_name = WEEKDAY_NAMES_MAP.get(target.weekday(), "")
        status_text = "오늘 매수일" if diff == 0 else f"D-{diff} ({target.strftime('%m-%d')} {day_name})"
        return target, diff, f"{desc} | {status_text}"

    if ctype == "bimonthly":
        # 짝수달 또는 격월 특정일
        cur_year = today.year
        cur_month = today.month

        def get_bimonthly_target(y: int, m: int) -> date:
            _, max_day = calendar.monthrange(y, m)
            day = max_day if cdetail == "LAST" else min(int(cdetail) if cdetail.isdigit() else 25, max_day)
            return date(y, m, day)

        candidate = get_bimonthly_target(cur_year, cur_month)
        if candidate >= today and (cur_month % 2 == 1):
            target = candidate
        else:
            # 다음 홀수달 또는 다음 달
            next_m = cur_month + 1 if candidate < today else cur_month
            y = cur_year + (next_m - 1) // 12
            m = ((next_m - 1) % 12) + 1
            target = get_bimonthly_target(y, m)

        diff = (target - today).days
        day_name = WEEKDAY_NAMES_MAP.get(target.weekday(), "")
        status_text = "오늘 매수일" if diff == 0 else f"D-{diff} ({target.strftime('%m-%d')} {day_name})"
        return target, diff, f"{desc} | {status_text}"

    if ctype == "quarterly":
        # 1월, 4월, 7월, 10월
        quarter_months = [1, 4, 7, 10]
        cur_year = today.year
        candidates = []
        for y in (cur_year, cur_year + 1):
            for m in quarter_months:
                _, max_day = calendar.monthrange(y, m)
                day = max_day if cdetail == "LAST" else min(int(cdetail) if cdetail.isdigit() else 25, max_day)
                d = date(y, m, day)
                if d >= today:
                    candidates.append(d)
        target = candidates[0] if candidates else today
        diff = (target - today).days
        day_name = WEEKDAY_NAMES_MAP.get(target.weekday(), "")
        status_text = "오늘 매수일" if diff == 0 else f"D-{diff} ({target.strftime('%m-%d')} {day_name})"
        return target, diff, f"{desc} | {status_text}"

    return None, None, desc


def get_current_cycle_period(
    cycle_type: str,
    cycle_detail: str = "",
    base_date: Optional[date] = None,
) -> Tuple[Optional[date], Optional[date], str]:
    """
    주기 유형에 따른 현재 주기의 시작일(start_date), 종료일(end_date), 주기 명칭(period_name)을 반환합니다.
    - monthly: 이번 달 1일 ~ 말일
    - weekly: 이번 주 월요일 ~ 일요일
    - biweekly: 이번 격주 14일 블록 (월~다음주 일)
    - bimonthly: 이번 격월 블록 (홀수달 1일 ~ 짝수달 말일)
    - quarterly: 이번 분기 블록 (분기 첫날 ~ 분기 마지막날)
    - daily: 오늘 하루 (base_date 당일)
    - none: (None, None, "수동 매수")
    """
    today = base_date or date.today()
    ctype = (cycle_type or "none").lower()
    cdetail = (cycle_detail or "").strip().upper()

    if ctype == "none":
        return None, None, "수동 매수"

    if ctype == "daily":
        return today, today, f"오늘 ({today.strftime('%Y-%m-%d')})"

    if ctype == "weekly":
        start_date = today - timedelta(days=today.weekday())
        end_date = start_date + timedelta(days=6)
        period_name = f"이번 주 ({start_date.strftime('%m/%d')}~{end_date.strftime('%m/%d')})"
        return start_date, end_date, period_name

    if ctype == "biweekly":
        # ISO 주차의 홀/짝 기준으로 2주 블록 정의
        iso_week = today.isocalendar().week
        week_start = today - timedelta(days=today.weekday())
        if iso_week % 2 == 0:
            start_date = week_start - timedelta(days=7)
        else:
            start_date = week_start
        end_date = start_date + timedelta(days=13)
        period_name = f"이번 격주 ({start_date.strftime('%m/%d')}~{end_date.strftime('%m/%d')})"
        return start_date, end_date, period_name

    if ctype == "monthly":
        start_date = date(today.year, today.month, 1)
        _, max_day = calendar.monthrange(today.year, today.month)
        end_date = date(today.year, today.month, max_day)
        period_name = f"이번 달 ({today.year}년 {today.month:02d}월)"
        return start_date, end_date, period_name

    if ctype == "bimonthly":
        start_m = ((today.month - 1) // 2) * 2 + 1
        end_m = start_m + 1
        start_date = date(today.year, start_m, 1)
        _, max_day = calendar.monthrange(today.year, end_m)
        end_date = date(today.year, end_m, max_day)
        period_name = f"이번 격월 ({start_m}월~{end_m}월)"
        return start_date, end_date, period_name

    if ctype == "quarterly":
        q_idx = (today.month - 1) // 3 + 1
        start_m = (q_idx - 1) * 3 + 1
        end_m = start_m + 2
        start_date = date(today.year, start_m, 1)
        _, max_day = calendar.monthrange(today.year, end_m)
        end_date = date(today.year, end_m, max_day)
        period_name = f"이번 분기 ({q_idx}분기: {start_m:02d}월~{end_m:02d}월)"
        return start_date, end_date, period_name

    # fallback
    start_date = date(today.year, today.month, 1)
    _, max_day = calendar.monthrange(today.year, today.month)
    end_date = date(today.year, today.month, max_day)
    return start_date, end_date, f"이번 달 ({today.year}년 {today.month:02d}월)"


def check_cycle_investment_history(
    transactions: list,
    cycle_type: str,
    cycle_detail: str = "",
    base_date: Optional[date] = None,
) -> Tuple[bool, Optional[str], str]:
    """
    현재 주기 기간 내에 BUY(매수/납입) 거래 내역이 존재하는지 확인합니다.
    반환: (has_bought, latest_buy_date_str, period_name)
    """
    start_date, end_date, period_name = get_current_cycle_period(cycle_type, cycle_detail, base_date)
    if start_date is None or end_date is None:
        return False, None, period_name

    latest_buy_dt = None
    for tx in transactions:
        tx_type = getattr(tx, "transaction_type", None)
        if isinstance(tx, dict):
            tx_type = tx.get("transaction_type", tx.get("type", ""))
            tx_date_str = str(tx.get("transaction_date", tx.get("date", "")))
        else:
            tx_date_str = str(getattr(tx, "transaction_date", ""))

        if not tx_type or tx_type.upper() != "BUY":
            continue

        try:
            tx_d = datetime.strptime(tx_date_str[:10], "%Y-%m-%d").date()
        except ValueError:
            continue

        if start_date <= tx_d <= end_date:
            if latest_buy_dt is None or tx_date_str > latest_buy_dt:
                latest_buy_dt = tx_date_str

    has_bought = (latest_buy_dt is not None)
    return has_bought, latest_buy_dt, period_name

