"""Generate due morning reports for opted-in users in Asia/Seoul."""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from core.config import load_config
from database.connection import init_db
from database.repository import Repository
from services.daily_report_service import DailyReportService

logger = logging.getLogger("RetirementPortfolio.MultiUserMorningReports")
SEOUL = ZoneInfo("Asia/Seoul")


def _is_due(settings, now: datetime) -> bool:
    report_time = getattr(settings, "morning_report_time", None)
    return bool(
        settings
        and settings.morning_report_enabled
        and report_time
        and now.time().replace(tzinfo=None) >= report_time
    )


def run_all_users(now: datetime | None = None) -> int:
    init_db()
    config = load_config()
    current = now.astimezone(SEOUL) if now else datetime.now(SEOUL)
    user_ids = Repository.get_morning_report_user_ids()

    if not user_ids:
        logger.info("모닝 리포트 활성 사용자가 없습니다.")
        return 0

    failures = 0
    for user_id in user_ids:
        try:
            repo = Repository(user_id=user_id)
            settings = repo.get_user_settings()
            if not _is_due(settings, current):
                continue

            # A generated report and a delivered Kakao message are separate
            # states. If Kakao failed after the report was saved, retry on the
            # next workflow run instead of suppressing delivery for the day.
            existing_report = repo.get_morning_report_for_date(current.date())
            if existing_report is not None:
                if not settings.kakao_enabled:
                    logger.info("오늘 리포트가 이미 생성됨: %s", user_id)
                    continue
                if getattr(existing_report, "kakao_sent_at", None) is not None:
                    logger.info("오늘 카카오 리포트가 이미 발송됨: %s", user_id)
                    continue
                logger.info("오늘 리포트는 생성됐지만 카카오 미발송 상태라 재시도: %s", user_id)

            logger.info("사용자별 모닝 리포트 생성 시작: %s", user_id)
            service = DailyReportService(config=config, repo=repo)
            ok, message, _ = service.generate_and_send(
                send_kakao=bool(settings.kakao_enabled),
                update_prices=True,
                force_kakao=bool(settings.kakao_enabled),
            )
            if ok:
                logger.info("사용자별 모닝 리포트 완료: %s", user_id)
            else:
                failures += 1
                logger.error("사용자별 모닝 리포트 실패: %s / %s", user_id, message)
        except Exception:
            failures += 1
            logger.exception("사용자별 모닝 리포트 예외: %s", user_id)

    if failures:
        logger.error("모닝 리포트 실패 사용자 수: %d", failures)
        return 1
    return 0


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    raise SystemExit(run_all_users())


if __name__ == "__main__":
    main()
