"""
core/logging_config.py
애플리케이션 전역 로깅을 설정합니다.
콘솔 출력과 함께 logs/app.log 및 logs/error.log에 안전하게 기록합니다.
"""

from __future__ import annotations
import logging
import sys
from core.paths import get_log_path, get_error_log_path


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """루트 로거 및 파일/스트림 핸들러를 설정합니다."""
    logger = logging.getLogger("RetirementPortfolio")
    logger.setLevel(level)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 콘솔 핸들러
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 일반 로그 파일 핸들러 (app.log)
    app_log_path = get_log_path()
    file_handler = logging.FileHandler(app_log_path, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # 에러 로그 파일 핸들러 (error.log)
    err_log_path = get_error_log_path()
    err_handler = logging.FileHandler(err_log_path, encoding="utf-8")
    err_handler.setLevel(logging.ERROR)
    err_handler.setFormatter(formatter)
    logger.addHandler(err_handler)

    return logger
