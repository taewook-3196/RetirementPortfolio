"""
core/paths.py
프로그램 루트 디렉터리 및 데이터/백업/로그/설정 파일 경로를 상대경로 기반으로 일관되게 관리합니다.
PyInstaller 빌드 환경(sys.frozen)에서도 임시 _MEIPASS 폴더가 아닌 실제 실행파일 위치를 참조합니다.
"""

from __future__ import annotations
import os
import sys
from pathlib import Path


def get_project_root() -> Path:
    """
    프로젝트 Root 디렉터리를 반환합니다.
    - PyInstaller 실행 파일(.exe)인 경우:
      1) dist/ 하위 폴더에서 실행된 경우: 소스코드 상위 프로젝트 폴더를 감지하여
         'python main.py' 실행 환경과 DB(portfolio.db) 및 설정(config.yaml)을 완전 연동/공유.
      2) 단독 배포 폴더로 외부 복사/이동된 경우: exe 파일이 위치한 폴더를 독립 루트로 사용.
    - 일반 Python 실행인 경우: 본 파일(core/paths.py)의 상위 상위 디렉터리
    """
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        # dist/<패키지명> 내부에서 실행된 경우 상위 프로젝트 루트 공유
        if exe_dir.parent.name.lower() == "dist":
            project_dir = exe_dir.parent.parent
            if (project_dir / "main.py").exists() or (project_dir / "portfolio.db").exists():
                return project_dir
        return exe_dir
    else:
        # core/paths.py 기준 프로젝트 루트
        return Path(__file__).resolve().parent.parent


def get_database_path() -> Path:
    """portfolio.db 파일 경로를 반환합니다."""
    return get_project_root() / "portfolio.db"


def get_config_path() -> Path:
    """config.yaml 파일 경로를 반환합니다."""
    return get_project_root() / "config.yaml"


def get_log_dir() -> Path:
    """logs 디렉터리 경로를 반환합니다."""
    path = get_project_root() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_log_path() -> Path:
    """기본 app.log 파일 경로를 반환합니다."""
    return get_log_dir() / "app.log"


def get_error_log_path() -> Path:
    """error.log 파일 경로를 반환합니다."""
    return get_log_dir() / "error.log"


def get_backup_dir() -> Path:
    """backup 디렉터리 경로를 반환합니다."""
    path = get_project_root() / "backup"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_export_dir() -> Path:
    """exports 디렉터리 경로를 반환합니다."""
    path = get_project_root() / "exports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_report_dir() -> Path:
    """모닝 모바일 웹 리포트가 저장되는 디렉터리 경로를 반환합니다."""
    path = get_export_dir() / "reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_import_dir() -> Path:
    """imports 디렉터리 경로를 반환합니다."""
    path = get_project_root() / "imports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_resource_path(relative_path: str = "") -> Path:
    """
    아이콘, 이미지 등 정적 리소스 파일 경로를 반환합니다.
    PyInstaller 패키징 환경(_MEIPASS), _internal 폴더, 및 일반 실행 환경 모두 지원합니다.
    """
    base_dir = getattr(sys, "_MEIPASS", None)
    if base_dir:
        res_dir = Path(base_dir) / relative_path
        if res_dir.exists():
            return res_dir

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        internal_res = exe_dir / "_internal" / relative_path
        if internal_res.exists():
            return internal_res
        exe_res = exe_dir / relative_path
        if exe_res.exists():
            return exe_res

    return get_project_root() / relative_path


def get_icon_path() -> Path:
    """기본 프로그램 아이콘(icon.ico) 경로를 반환합니다."""
    return get_resource_path("resources/icon.ico")


def get_golden_pig_path() -> Path:
    """황금복돼지 스플래시 이미지(resources/golden_pig.png) 경로를 반환합니다."""
    return get_resource_path("resources/golden_pig.png")


def get_golden_pig_gif_path() -> Path:
    """황금복돼지 스플래시 GIF 애니메이션(resources/golden_pig.gif) 경로를 반환합니다."""
    return get_resource_path("resources/golden_pig.gif")


def ensure_directories() -> None:
    """프로그램 실행에 필요한 기본 폴더들을 생성합니다."""
    get_log_dir()
    get_backup_dir()
    get_export_dir()
    get_import_dir()
    (get_project_root() / "resources").mkdir(parents=True, exist_ok=True)
