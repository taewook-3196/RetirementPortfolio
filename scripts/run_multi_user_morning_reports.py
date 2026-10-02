"""Generate private morning reports for every opted-in user.

This runner deliberately has no REPORT_USER_ID. The enabled users are read from
user_settings and every DailyReportService receives an explicitly scoped
Repository. One user's failure does not stop reports for the remaining users.
"""

from __future__ import annotations

import logging
import sys

from core.config import load_config
from database.connection import init_db
from database.repository import Repository
from services.daily_report_service import DailyReportService

logger = logging.getLogger("RetirementPortfolio.MultiUserMorningReports")


def run_all_users() -> int:
    init_db()
    config = load_config()
    user_ids = Repository.get_morning_report_user_ids()

    if not user_ids:
        logger.info("모닝 리포트 활성 사용자가 없습니다.")
        return 0

    failures = 0
    for user_id in user_ids:
        repo = Repository(user_id=user_id)
        settings = repo.get_user_settings()
        if settings is None or not settings.morning_report_enabled:
            continue

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

    if failures:
        logger.error("모닝 리포트 실패 사용자 수: %d", failures)
        return 1
    return 0


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    raise SystemExit(run_all_users())


if __name__ == "__main__":
    main()
