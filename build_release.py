"""
build_release.py
개인 퇴직연금 ETF 포트폴리오 관리 시스템 배포용 빌드 스크립트.

실행 방법:
    python build_release.py                 # 기본: 배포용 단일 실행파일(onefile) 빌드
    python build_release.py --mode onedir   # 폴더 배포(onedir) 모드 빌드
    python build_release.py --clean         # 빌드 캐시(build, dist) 완전 정리 후 빌드
    python build_release.py --console       # 디버깅용 콘솔 창 포함 빌드
"""

from __future__ import annotations
import os
import sys
import time
import shutil
import argparse
from pathlib import Path

# Windows 콘솔 인코딩 대응
if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import PyInstaller.__main__


def get_file_size_str(path: Path) -> str:
    """파일 크기를 읽기 쉬운 문자열로 반환합니다."""
    if not path.exists():
        return "0 B"
    size_bytes = path.stat().st_size
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def clean_build_artifacts(root_dir: Path):
    """기존 빌드 캐시 및 산출물 폴더를 정리합니다."""
    print("[정리] 이전 빌드 임시 파일 정리 중...")
    for folder_name in ["build", "__pycache__"]:
        p = root_dir / folder_name
        if p.exists() and p.is_dir():
            try:
                shutil.rmtree(p, ignore_errors=True)
            except Exception as e:
                print(f"   [경고] {folder_name} 삭제 중 오류: {e}")

    # .spec 파일 캐시 정리 (필요시)
    for spec in root_dir.glob("*.spec"):
        if spec.name != "RetirementPortfolio.spec":
            try:
                spec.unlink()
            except Exception:
                pass


def build_release(
    mode: str = "onedir",
    app_name: str = "RetirementPortfolio",
    clean: bool = False,
    show_console: bool = False,
) -> bool:
    """
    PyInstaller를 호출하여 배포용 실행 파일을 생성합니다.
    """
    start_time = time.time()
    root_dir = Path(__file__).resolve().parent

    print("=" * 65)
    print("[시작] 개인 퇴직연금 ETF 포트폴리오 관리 시스템 배포용 빌드")
    print(f"   - 작업 경로: {root_dir}")
    print(f"   - 빌드 모드: {'디렉터리 패키징 (One-dir - 권장)' if mode == 'onedir' else '단일 실행파일 (One-file)'}")
    print(f"   - 콘솔 창:   {'표시 (디버그 모드)' if show_console else '숨김 (GUI 전용)'}")
    print(f"   - 대상 파일: {app_name}.exe")
    print("=" * 65)

    # 1. 필수 리소스 확인
    icon_path = root_dir / "resources" / "icon.ico"
    if not icon_path.exists():
        print(f"[경고] 아이콘 파일을 찾을 수 없습니다: {icon_path}")

    entry_point = root_dir / "main.py"
    if not entry_point.exists():
        print(f"[오류] 진입점 파일(main.py)이 존재하지 않습니다: {entry_point}")
        return False

    # 2. 클린 빌드 및 기존 충돌 파일 정리
    if clean:
        clean_build_artifacts(root_dir)
    elif mode == "onedir":
        # dist 루트에 있는 단일 exe 파일이 있으면 사용자 혼동 방지를 위해 삭제
        root_exe = root_dir / "dist" / f"{app_name}.exe"
        if root_exe.exists() and root_exe.is_file():
            try:
                root_exe.unlink()
            except Exception:
                pass

    # 3. 데이터 및 리소스 번들링 인자 구성
    sep = ";" if sys.platform == "win32" else ":"
    datas = [
        f"resources{sep}resources",
        f"comment.txt{sep}.",
        f"config.yaml{sep}.",
    ]

    # 4. Hidden Imports 구성
    hidden_imports = [
        "truststore",
        "sqlalchemy",
        "sqlalchemy.dialects.sqlite",
        "yaml",
        "dotenv",
        "requests",
        "urllib3",
        "matplotlib",
        "matplotlib.backends.backend_qtagg",
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "strategy.cycle_helper",
        "strategy.recommendation",
        "strategy.rebalancing",
        "data.etf_seeds",
        "data.krx_client",
        "data.mock_provider",
        "data.price_updater",
        "services.news_service",
        "services.report_html_generator",
        "services.kakao_service",
        "services.daily_report_service",
        "services.github_service",
    ]

    # 5. 불필요한 패키지 제외 (용량 및 빌드 속도 최적화, matplotlib 의존성인 unittest는 유지)
    excludes = [
        "tkinter",
        "torch",
        "scipy",
        "cv2",
        "IPython",
        "notebook",
    ]

    # 6. PyInstaller 명령줄 인자 조합
    args = [
        str(entry_point),
        f"--name={app_name}",
        "--noconfirm",
    ]

    if mode == "onefile":
        args.append("--onefile")
    else:
        args.append("--onedir")

    if show_console:
        args.append("--console")
    else:
        args.append("--noconsole")

    if icon_path.exists():
        args.append(f"--icon={icon_path}")

    for d in datas:
        args.append(f"--add-data={d}")

    for hi in hidden_imports:
        args.append(f"--hidden-import={hi}")

    for ex in excludes:
        args.append(f"--exclude-module={ex}")

    # 7. PyInstaller 실행
    print("\n[진행] PyInstaller 패키징을 실행합니다...")
    try:
        PyInstaller.__main__.run(args)
    except SystemExit as e:
        if e.code != 0:
            print(f"\n[오류] PyInstaller 빌드 중 오류 발생 (종료 코드: {e.code})")
            return False
    except Exception as e:
        print(f"\n[오류] 빌드 실행 중 예외 발생: {e}")
        return False

    # 8. 빌드 후처리: 배포용 부속 파일 복사 (dist 폴더에 함께 제공)
    dist_dir = root_dir / "dist"
    target_deploy_dir = dist_dir if mode == "onefile" else (dist_dir / app_name)

    print("\n[배치] 배포용 설정 및 보조 파일 배치 중...")
    deploy_assets = ["config.yaml", "comment.txt", ".env.example"]
    for asset in deploy_assets:
        src = root_dir / asset
        if src.exists():
            dst = target_deploy_dir / asset
            try:
                shutil.copy2(src, dst)
                print(f"   - 복사 완료: {asset} -> {dst.name}")
            except Exception as e:
                print(f"   [주의] {asset} 복사 실패: {e}")

    # 9. 결과 보고
    elapsed = time.time() - start_time
    if mode == "onefile":
        target_exe = dist_dir / f"{app_name}.exe"
    else:
        target_exe = dist_dir / app_name / f"{app_name}.exe"

    print("\n" + "=" * 65)
    if target_exe.exists():
        print("[완료] 배포용 실행 파일이 성공적으로 생성되었습니다!")
        print(f"   - 파일 위치: {target_exe}")
        print(f"   - 파일 크기: {get_file_size_str(target_exe)}")
        print(f"   - 소요 시간: {elapsed:.1f}초")
        print("\n[배포 안내]")
        if mode == "onefile":
            print(f"   1. 'dist/{app_name}.exe' 파일을 복사하여 어디서든 단독 실행할 수 있습니다.")
            print(f"   2. 사용자 설정 변경이 필요한 경우 같은 폴더에 'config.yaml' 또는 '.env'를 두시면 자동 연동됩니다.")
        else:
            print(f"   1. 'dist/{app_name}/' 폴더 전체를 배포 대상으로 압축(ZIP)하여 전달하세요.")
            print(f"   2. 폴더 내부의 '{app_name}.exe'를 실행하면 즉시 구동됩니다.")
    else:
        print("[경고] 빌드 프로세스는 완료되었으나 대상 실행 파일을 확인하지 못했습니다.")
        print(f"   확인 대상: {target_exe}")
    print("=" * 65)

    return target_exe.exists()


def main():
    parser = argparse.ArgumentParser(description="개인 퇴직연금 ETF 포트폴리오 관리 시스템 배포 빌더")
    parser.add_argument(
        "--mode",
        choices=["onedir", "onefile"],
        default="onedir",
        help="빌드 모드 (onedir: 폴더 패키지-기본값/권장, onefile: 단일 exe 파일)",
    )
    parser.add_argument(
        "--name",
        default="RetirementPortfolio",
        help="생성할 실행 파일 명칭 (기본값: RetirementPortfolio)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="빌드 전 이전 임시/캐시 폴더를 정리합니다.",
    )
    parser.add_argument(
        "--console",
        action="store_true",
        help="디버깅을 위해 콘솔 창을 활성화합니다.",
    )

    args = parser.parse_args()
    success = build_release(
        mode=args.mode,
        app_name=args.name,
        clean=args.clean,
        show_console=args.console,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
