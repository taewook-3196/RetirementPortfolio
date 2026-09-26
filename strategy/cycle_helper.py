"""
strategy/cycle_helper.py

개인별/계좌별 매수 투자 주기 및
다음 정기 매수 검토 기준일(D-day) 계산 유틸리티.

지원 주기:
- none: 주기 없음
- daily: 매일
- weekly: 매주
- biweekly: 격주
- monthly: 매월
- bimonthly: 격월
- quarterly: 분기

PostgreSQL/Supabase에서 반환되는
date / datetime 타입도 직접 처리합니다.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Any, Optional, Tuple


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


VALID_CYCLE_TYPES = {
    "none",
    "daily",
    "weekly",
    "biweekly",
    "monthly",
    "bimonthly",
    "quarterly",
}


def _normalize_cycle_type(
    cycle_type: str,
) -> str:
    """
    주기 유형을 정규화합니다.

    알 수 없는 값은 기존 기본값인 monthly로 처리합니다.
    """
    value = str(
        cycle_type or "none"
    ).strip().lower()

    if value in VALID_CYCLE_TYPES:
        return value

    return "monthly"


def _normalize_cycle_detail(
    cycle_detail: str,
) -> str:
    """주기 상세값을 정규화합니다."""
    return str(
        cycle_detail or ""
    ).strip().upper()


def _safe_month_day(
    cycle_detail: str,
    default_day: int = 25,
) -> Optional[int]:
    """
    월간/격월/분기 매수일을 안전하게 해석합니다.

    LAST이면 None을 반환합니다.
    숫자값은 1~31 범위로 제한합니다.
    """
    detail = _normalize_cycle_detail(
        cycle_detail
    )

    if detail == "LAST":
        return None

    if not detail.isdigit():
        return default_day

    day = int(detail)

    return max(
        1,
        min(
            day,
            31,
        ),
    )


def _make_month_target(
    year: int,
    month: int,
    cycle_detail: str,
) -> date:
    """
    특정 연/월의 투자 예정일을 생성합니다.

    예:
    - 25 -> 해당 월 25일
    - 31 -> 2월이면 실제 말일
    - LAST -> 해당 월 말일
    """
    _, max_day = calendar.monthrange(
        year,
        month,
    )

    configured_day = _safe_month_day(
        cycle_detail
    )

    if configured_day is None:
        day = max_day
    else:
        day = min(
            configured_day,
            max_day,
        )

    return date(
        year,
        month,
        day,
    )


def _add_months(
    year: int,
    month: int,
    months: int,
) -> Tuple[int, int]:
    """
    연/월에 지정한 개월 수를 더합니다.

    반환:
        (year, month)
    """
    month_index = (
        year * 12
        + (month - 1)
        + months
    )

    new_year = (
        month_index // 12
    )

    new_month = (
        month_index % 12
        + 1
    )

    return (
        new_year,
        new_month,
    )


def _format_status(
    today: date,
    target: date,
) -> Tuple[int, str]:
    """
    예정일 기준 D-day와 표시 문자열을 반환합니다.
    """
    diff = (
        target - today
    ).days

    if diff == 0:
        return (
            0,
            "오늘 정기 매수 검토 기준일",
        )

    day_name = WEEKDAY_NAMES_MAP.get(
        target.weekday(),
        "",
    )

    return (
        diff,
        (
            f"D-{diff} "
            f"({target.strftime('%m-%d')} "
            f"{day_name})"
        ),
    )


def _parse_transaction_date(
    value: Any,
) -> Optional[date]:
    """
    거래일 값을 date로 변환합니다.

    지원:
    - datetime
    - date
    - YYYY-MM-DD 문자열
    - YYYYMMDD 문자열
    """
    if value is None:
        return None

    if isinstance(
        value,
        datetime,
    ):
        return value.date()

    if isinstance(
        value,
        date,
    ):
        return value

    text = str(
        value
    ).strip()

    if not text:
        return None

    # datetime 문자열이 들어온 경우
    # 날짜 부분만 사용
    if len(text) >= 10:
        first_ten = text[:10]

        try:
            return datetime.strptime(
                first_ten,
                "%Y-%m-%d",
            ).date()
        except ValueError:
            pass

    compact = text.replace(
        "-",
        "",
    )[:8]

    try:
        return datetime.strptime(
            compact,
            "%Y%m%d",
        ).date()
    except ValueError:
        return None


def format_cycle_description(
    cycle_type: str,
    cycle_detail: str,
) -> str:
    """
    주기 유형과 세부 설정을
    한글 설명으로 반환합니다.
    """
    ctype = _normalize_cycle_type(
        cycle_type
    )

    cdetail = _normalize_cycle_detail(
        cycle_detail
    )

    if ctype == "none":
        return "수동 매수 (주기 없음)"

    if ctype == "daily":
        return "매일 (영업일 매수)"

    if ctype == "weekly":
        day_kr = WEEKDAYS_KR.get(
            cdetail,
            ("화요일", 1),
        )[0]

        return f"매주 {day_kr}"

    if ctype == "biweekly":
        day_kr = WEEKDAYS_KR.get(
            cdetail,
            ("금요일", 4),
        )[0]

        return f"격주 {day_kr}"

    if ctype == "monthly":
        if cdetail == "LAST":
            return "매월 말일"

        day_num = _safe_month_day(
            cdetail
        )

        return f"매월 {day_num}일"

    if ctype == "bimonthly":
        if cdetail == "LAST":
            return "격월 말일"

        day_num = _safe_month_day(
            cdetail
        )

        return f"격월 {day_num}일"

    if ctype == "quarterly":
        if cdetail == "LAST":
            return (
                "분기 말일 "
                "(1/4/7/10월)"
            )

        day_num = _safe_month_day(
            cdetail
        )

        return (
            f"분기별 {day_num}일 "
            "(1/4/7/10월)"
        )

    return "매월 25일"


def calculate_next_investment_date(
    cycle_type: str,
    cycle_detail: str,
    base_date: Optional[date] = None,
) -> Tuple[
    Optional[date],
    Optional[int],
    str,
]:
    """
    주기 유형 및 세부 설정을 바탕으로
    다음 정기 매수 검토 기준일, D-day, 설명을 반환합니다.

    반환:
        (
            next_date,
            days_remaining,
            display_str,
        )

    days_remaining:
    - 0: 오늘 정기 매수 검토 기준일
    - 양수: 다음 정기 매수 검토 기준일까지 남은 일수
    - None: 주기 없음
    """
    today = (
        base_date
        or date.today()
    )

    ctype = _normalize_cycle_type(
        cycle_type
    )

    cdetail = _normalize_cycle_detail(
        cycle_detail
    )

    desc = format_cycle_description(
        ctype,
        cdetail,
    )

    # -------------------------------------------------------------
    # 주기 없음
    # -------------------------------------------------------------

    if ctype == "none":
        return (
            None,
            None,
            f"{desc} | 계획에 따라 자유 매수",
        )

    # -------------------------------------------------------------
    # 매일
    # -------------------------------------------------------------

    if ctype == "daily":
        # 월~금이면 오늘
        if today.weekday() < 5:
            target = today

        # 토요일 -> 월요일
        elif today.weekday() == 5:
            target = (
                today
                + timedelta(days=2)
            )

        # 일요일 -> 월요일
        else:
            target = (
                today
                + timedelta(days=1)
            )

        diff, status_text = (
            _format_status(
                today,
                target,
            )
        )

        return (
            target,
            diff,
            f"{desc} | {status_text}",
        )

    # -------------------------------------------------------------
    # 매주
    # -------------------------------------------------------------

    if ctype == "weekly":
        target_weekday = (
            WEEKDAYS_KR.get(
                cdetail,
                ("화요일", 1),
            )[1]
        )

        days_ahead = (
            target_weekday
            - today.weekday()
        ) % 7

        target = (
            today
            + timedelta(
                days=days_ahead
            )
        )

        diff, status_text = (
            _format_status(
                today,
                target,
            )
        )

        return (
            target,
            diff,
            f"{desc} | {status_text}",
        )

    # -------------------------------------------------------------
    # 격주
    # -------------------------------------------------------------

    if ctype == "biweekly":
        target_weekday = (
            WEEKDAYS_KR.get(
                cdetail,
                ("금요일", 4),
            )[1]
        )

        current_week_start = (
            today
            - timedelta(
                days=today.weekday()
            )
        )

        iso_week = (
            current_week_start
            .isocalendar()
            .week
        )

        # 현재 구현에서는 홀수 ISO 주차를
        # 격주 투자 주간으로 사용합니다.
        if iso_week % 2 == 1:
            investment_week_start = (
                current_week_start
            )
        else:
            investment_week_start = (
                current_week_start
                + timedelta(days=7)
            )

        target = (
            investment_week_start
            + timedelta(
                days=target_weekday
            )
        )

        # 홀수 주차인데 해당 요일이 이미 지났다면
        # 다음 격주 투자 주간으로 이동
        if target < today:
            target = (
                target
                + timedelta(days=14)
            )

        diff, status_text = (
            _format_status(
                today,
                target,
            )
        )

        return (
            target,
            diff,
            f"{desc} | {status_text}",
        )

    # -------------------------------------------------------------
    # 매월
    # -------------------------------------------------------------

    if ctype == "monthly":
        target = _make_month_target(
            today.year,
            today.month,
            cdetail,
        )

        if target < today:
            next_year, next_month = (
                _add_months(
                    today.year,
                    today.month,
                    1,
                )
            )

            target = _make_month_target(
                next_year,
                next_month,
                cdetail,
            )

        diff, status_text = (
            _format_status(
                today,
                target,
            )
        )

        return (
            target,
            diff,
            f"{desc} | {status_text}",
        )

    # -------------------------------------------------------------
    # 격월
    # -------------------------------------------------------------

    if ctype == "bimonthly":
        # 격월 블록:
        # 1~2월, 3~4월, 5~6월, ...
        #
        # 실제 매수월은 각 블록의 첫 달:
        # 1, 3, 5, 7, 9, 11월

        current_block_start_month = (
            ((today.month - 1) // 2)
            * 2
            + 1
        )

        target = _make_month_target(
            today.year,
            current_block_start_month,
            cdetail,
        )

        # 현재 격월 블록의 투자일이 지났으면
        # 다음 격월 블록으로 이동
        if target < today:
            next_year, next_month = (
                _add_months(
                    today.year,
                    current_block_start_month,
                    2,
                )
            )

            target = _make_month_target(
                next_year,
                next_month,
                cdetail,
            )

        diff, status_text = (
            _format_status(
                today,
                target,
            )
        )

        return (
            target,
            diff,
            f"{desc} | {status_text}",
        )

    # -------------------------------------------------------------
    # 분기
    # -------------------------------------------------------------

    if ctype == "quarterly":
        quarter_months = (
            1,
            4,
            7,
            10,
        )

        target: Optional[date] = None

        for year in (
            today.year,
            today.year + 1,
        ):
            for month in quarter_months:
                candidate = (
                    _make_month_target(
                        year,
                        month,
                        cdetail,
                    )
                )

                if candidate >= today:
                    target = candidate
                    break

            if target is not None:
                break

        if target is None:
            # 이론적으로 도달하지 않지만
            # 안전한 fallback
            target = _make_month_target(
                today.year + 1,
                1,
                cdetail,
            )

        diff, status_text = (
            _format_status(
                today,
                target,
            )
        )

        return (
            target,
            diff,
            f"{desc} | {status_text}",
        )

    return (
        None,
        None,
        desc,
    )


def get_current_cycle_period(
    cycle_type: str,
    cycle_detail: str = "",
    base_date: Optional[date] = None,
) -> Tuple[
    Optional[date],
    Optional[date],
    str,
]:
    """
    현재 투자 주기의 시작일, 종료일,
    주기 설명을 반환합니다.

    반환:
        (
            start_date,
            end_date,
            period_name,
        )
    """
    today = (
        base_date
        or date.today()
    )

    ctype = _normalize_cycle_type(
        cycle_type
    )

    # -------------------------------------------------------------
    # 주기 없음
    # -------------------------------------------------------------

    if ctype == "none":
        return (
            None,
            None,
            "수동 매수",
        )

    # -------------------------------------------------------------
    # 매일
    # -------------------------------------------------------------

    if ctype == "daily":
        return (
            today,
            today,
            (
                "오늘 "
                f"({today.strftime('%Y-%m-%d')})"
            ),
        )

    # -------------------------------------------------------------
    # 매주
    # -------------------------------------------------------------

    if ctype == "weekly":
        start_date = (
            today
            - timedelta(
                days=today.weekday()
            )
        )

        end_date = (
            start_date
            + timedelta(days=6)
        )

        period_name = (
            "이번 주 "
            f"({start_date.strftime('%m/%d')}"
            "~"
            f"{end_date.strftime('%m/%d')})"
        )

        return (
            start_date,
            end_date,
            period_name,
        )

    # -------------------------------------------------------------
    # 격주
    # -------------------------------------------------------------

    if ctype == "biweekly":
        week_start = (
            today
            - timedelta(
                days=today.weekday()
            )
        )

        iso_week = (
            week_start
            .isocalendar()
            .week
        )

        # calculate_next_investment_date와 동일하게
        # 홀수 ISO 주차를 격주 블록의 첫 주로 사용
        if iso_week % 2 == 1:
            start_date = (
                week_start
            )
        else:
            start_date = (
                week_start
                - timedelta(days=7)
            )

        end_date = (
            start_date
            + timedelta(days=13)
        )

        period_name = (
            "이번 격주 "
            f"({start_date.strftime('%m/%d')}"
            "~"
            f"{end_date.strftime('%m/%d')})"
        )

        return (
            start_date,
            end_date,
            period_name,
        )

    # -------------------------------------------------------------
    # 매월
    # -------------------------------------------------------------

    if ctype == "monthly":
        start_date = date(
            today.year,
            today.month,
            1,
        )

        _, max_day = (
            calendar.monthrange(
                today.year,
                today.month,
            )
        )

        end_date = date(
            today.year,
            today.month,
            max_day,
        )

        period_name = (
            "이번 달 "
            f"({today.year}년 "
            f"{today.month:02d}월)"
        )

        return (
            start_date,
            end_date,
            period_name,
        )

    # -------------------------------------------------------------
    # 격월
    # -------------------------------------------------------------

    if ctype == "bimonthly":
        start_month = (
            ((today.month - 1) // 2)
            * 2
            + 1
        )

        end_month = (
            start_month + 1
        )

        start_date = date(
            today.year,
            start_month,
            1,
        )

        _, max_day = (
            calendar.monthrange(
                today.year,
                end_month,
            )
        )

        end_date = date(
            today.year,
            end_month,
            max_day,
        )

        period_name = (
            "이번 격월 "
            f"({start_month}월"
            "~"
            f"{end_month}월)"
        )

        return (
            start_date,
            end_date,
            period_name,
        )

    # -------------------------------------------------------------
    # 분기
    # -------------------------------------------------------------

    if ctype == "quarterly":
        quarter_index = (
            (today.month - 1)
            // 3
            + 1
        )

        start_month = (
            (quarter_index - 1)
            * 3
            + 1
        )

        end_month = (
            start_month + 2
        )

        start_date = date(
            today.year,
            start_month,
            1,
        )

        _, max_day = (
            calendar.monthrange(
                today.year,
                end_month,
            )
        )

        end_date = date(
            today.year,
            end_month,
            max_day,
        )

        period_name = (
            "이번 분기 "
            f"({quarter_index}분기: "
            f"{start_month:02d}월"
            "~"
            f"{end_month:02d}월)"
        )

        return (
            start_date,
            end_date,
            period_name,
        )

    # -------------------------------------------------------------
    # fallback
    # -------------------------------------------------------------

    start_date = date(
        today.year,
        today.month,
        1,
    )

    _, max_day = (
        calendar.monthrange(
            today.year,
            today.month,
        )
    )

    end_date = date(
        today.year,
        today.month,
        max_day,
    )

    return (
        start_date,
        end_date,
        (
            "이번 달 "
            f"({today.year}년 "
            f"{today.month:02d}월)"
        ),
    )


def check_cycle_investment_history(
    transactions: list,
    cycle_type: str,
    cycle_detail: str = "",
    base_date: Optional[date] = None,
) -> Tuple[
    bool,
    Optional[str],
    str,
]:
    """
    현재 투자 주기 안에 BUY 거래가 존재하는지 확인합니다.

    SQLAlchemy Transaction 객체와 dict를 모두 지원합니다.

    PostgreSQL에서 transaction_date가 date 객체로 반환되어도
    문자열 변환 없이 직접 처리할 수 있습니다.

    반환:
        (
            has_bought,
            latest_buy_date_str,
            period_name,
        )
    """
    (
        start_date,
        end_date,
        period_name,
    ) = get_current_cycle_period(
        cycle_type,
        cycle_detail,
        base_date,
    )

    if (
        start_date is None
        or end_date is None
    ):
        return (
            False,
            None,
            period_name,
        )

    latest_buy_date: Optional[
        date
    ] = None

    for transaction in (
        transactions or []
    ):
        # ---------------------------------------------------------
        # dict 형태
        # ---------------------------------------------------------

        if isinstance(
            transaction,
            dict,
        ):
            transaction_type = (
                transaction.get(
                    "transaction_type",
                    transaction.get(
                        "type",
                        "",
                    ),
                )
            )

            transaction_date_value = (
                transaction.get(
                    "transaction_date",
                    transaction.get(
                        "date",
                        None,
                    ),
                )
            )

        # ---------------------------------------------------------
        # SQLAlchemy 객체 형태
        # ---------------------------------------------------------

        else:
            transaction_type = getattr(
                transaction,
                "transaction_type",
                "",
            )

            transaction_date_value = getattr(
                transaction,
                "transaction_date",
                None,
            )

        # ---------------------------------------------------------
        # BUY만 확인
        # ---------------------------------------------------------

        tx_type = str(
            transaction_type or ""
        ).strip().upper()

        if tx_type != "BUY":
            continue

        # ---------------------------------------------------------
        # 날짜 정규화
        # ---------------------------------------------------------

        transaction_date = (
            _parse_transaction_date(
                transaction_date_value
            )
        )

        if transaction_date is None:
            continue

        # ---------------------------------------------------------
        # 현재 주기 안의 거래인지 확인
        # ---------------------------------------------------------

        if (
            start_date
            <= transaction_date
            <= end_date
        ):
            if (
                latest_buy_date is None
                or transaction_date
                > latest_buy_date
            ):
                latest_buy_date = (
                    transaction_date
                )

    # -------------------------------------------------------------
    # 결과
    # -------------------------------------------------------------

    if latest_buy_date is None:
        return (
            False,
            None,
            period_name,
        )

    return (
        True,
        latest_buy_date.strftime(
            "%Y-%m-%d"
        ),
        period_name,
    )

def get_cycle_buy_amount(
    transactions: list,
    cycle_type: str,
    cycle_detail: str = "",
    base_date: Optional[date] = None,
) -> Tuple[
    float,
    Optional[str],
    str,
]:
    """
    현재 투자 주기 안에서 실제 BUY 거래금액 합계를 계산합니다.

    거래금액 계산:
        quantity * price + fee + tax

    반환:
        (
            total_buy_amount,
            latest_buy_date_str,
            period_name,
        )
    """
    (
        start_date,
        end_date,
        period_name,
    ) = get_current_cycle_period(
        cycle_type,
        cycle_detail,
        base_date,
    )

    if (
        start_date is None
        or end_date is None
    ):
        return (
            0.0,
            None,
            period_name,
        )

    total_buy_amount = 0.0
    latest_buy_date: Optional[date] = None

    for transaction in (
        transactions or []
    ):
        if isinstance(
            transaction,
            dict,
        ):
            transaction_type = (
                transaction.get(
                    "transaction_type",
                    transaction.get(
                        "type",
                        "",
                    ),
                )
            )

            transaction_date_value = (
                transaction.get(
                    "transaction_date",
                    transaction.get(
                        "date",
                        None,
                    ),
                )
            )

            quantity = transaction.get(
                "quantity",
                0,
            )

            price = transaction.get(
                "price",
                0,
            )

            fee = transaction.get(
                "fee",
                0,
            )

            tax = transaction.get(
                "tax",
                0,
            )

        else:
            transaction_type = getattr(
                transaction,
                "transaction_type",
                "",
            )

            transaction_date_value = getattr(
                transaction,
                "transaction_date",
                None,
            )

            quantity = getattr(
                transaction,
                "quantity",
                0,
            )

            price = getattr(
                transaction,
                "price",
                0,
            )

            fee = getattr(
                transaction,
                "fee",
                0,
            )

            tax = getattr(
                transaction,
                "tax",
                0,
            )

        tx_type = str(
            transaction_type or ""
        ).strip().upper()

        if tx_type != "BUY":
            continue

        transaction_date = (
            _parse_transaction_date(
                transaction_date_value
            )
        )

        if transaction_date is None:
            continue

        if not (
            start_date
            <= transaction_date
            <= end_date
        ):
            continue

        quantity_value = max(
            0.0,
            float(
                quantity or 0
            ),
        )

        price_value = max(
            0.0,
            float(
                price or 0
            ),
        )

        fee_value = max(
            0.0,
            float(
                fee or 0
            ),
        )

        tax_value = max(
            0.0,
            float(
                tax or 0
            ),
        )

        buy_amount = (
            quantity_value
            * price_value
            + fee_value
            + tax_value
        )

        total_buy_amount += buy_amount

        if (
            latest_buy_date is None
            or transaction_date
            > latest_buy_date
        ):
            latest_buy_date = (
                transaction_date
            )

    latest_buy_date_str = (
        latest_buy_date.strftime(
            "%Y-%m-%d"
        )
        if latest_buy_date
        else None
    )

    return (
        total_buy_amount,
        latest_buy_date_str,
        period_name,
    )
