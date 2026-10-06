"""Generate due morning reports for opted-in users in Asia/Seoul."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from core.config import load_config
from database.connection import init_db
from database.repository import Repository
from services.daily_report_service import DailyReportService
from data.price_updater import update_market_prices

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


class _CombinedMarketRepository:
    """Expose all due users' tickers while writing shared market data once."""

    user_id = "multi-user-market-sync"

    def __init__(self, repositories):
        self.repositories = list(repositories)
        self.shared = self.repositories[0]

    def get_account_targets(self, account_id=None):
        return [
            target
            for repo in self.repositories
            for target in repo.get_account_targets(account_id=account_id)
        ]

    def get_transactions(self):
        return [
            tx
            for repo in self.repositories
            for tx in repo.get_transactions()
        ]

    def get_etf_master(self, ticker):
        return self.shared.get_etf_master(ticker)

    def save_etf_master(self, items):
        return self.shared.save_etf_master(items)

    def upsert_prices(self, items):
        return self.shared.upsert_prices(items)


def run_all_users(now: datetime | None = None, force: bool = False) -> int:
    init_db()
    config = load_config()
    current = now.astimezone(SEOUL) if now else datetime.now(SEOUL)
    user_ids = Repository.get_morning_report_user_ids()

    if not user_ids:
        logger.info("모닝 리포트 활성 사용자가 없습니다.")
        return 0

    failures = 0
    due_users = []
    for user_id in user_ids:
        try:
            repo = Repository(user_id=user_id)
            settings = repo.get_user_settings()
            if not force and not _is_due(settings, current):
                continue
            due_users.append((user_id, repo, settings))
        except Exception:
            failures += 1
            logger.exception("모닝 리포트 대상 사용자 확인 예외: %s", user_id)

    if due_users:
        try:
            combined_repo = _CombinedMarketRepository(
                [repo for _, repo, _ in due_users]
            )
            update_market_prices(
                config=config,
                repo=combined_repo,
                days=5,
            )
            logger.info(
                "다중 사용자 공용 시장 가격 동기화 완료: 사용자 %d명",
                len(due_users),
            )
        except Exception:
            logger.exception(
                "공용 시장 가격 동기화 실패 (기존 DB 캐시로 계속 진행)"
            )

    for user_id, repo, settings in due_users:
        try:

            # A generated report and a delivered Kakao message are separate
            # states. If Kakao failed after the report was saved, retry on the
            # next workflow run instead of suppressing delivery for the day.
            existing_report = repo.get_morning_report_for_date(current.date())
            if existing_report is not None and not force:
                if not settings.kakao_enabled:
                    logger.info("오늘 리포트가 이미 생성됨: %s", user_id)
                    continue
                if getattr(existing_report, "kakao_sent_at", None) is not None:
                    logger.info("오늘 카카오 리포트가 이미 발송됨: %s", user_id)
                    continue
                logger.info("오늘 리포트는 생성됐지만 카카오 미발송 상태라 재시도: %s", user_id)

            if force and existing_report is not None:
                logger.info("수동 강제 재생성·재발송: %s", user_id)

            logger.info("사용자별 모닝 리포트 생성 시작: %s", user_id)
            service = DailyReportService(config=config, repo=repo)
            ok, message, _ = service.generate_and_send(
                send_kakao=bool(settings.kakao_enabled),
                update_prices=False,
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
    force = os.getenv("FORCE_MORNING_REPORT", "").strip().lower() in {"1", "true", "yes"}
    raise SystemExit(run_all_users(force=force))


if __name__ == "__main__":
    main()
