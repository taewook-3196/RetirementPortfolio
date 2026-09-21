"""
scripts/upload_to_github.py
Git 설치 없이 GitHub REST API(Git Data API)를 통해
프로젝트 파일들을 내 GitHub 저장소로 자동 업로드(초기 커밋)하는 스크립트.
"""

import os
import sys
import ssl
import json
import base64
import urllib.request
import urllib.parse
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from core.config import load_config

if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def main():
    print("=" * 70)
    print("   GitHub 저장소 원격 파일 업로드 (Git 미설치 환경 대응)")
    print("=" * 70)

    config = load_config()
    m_cfg = config.morning_report

    repo_full = m_cfg.github_repo.strip()
    if "github.com/" in repo_full:
        repo_full = repo_full.split("github.com/")[1].strip("/").removesuffix(".git")

    token = m_cfg.github_token.strip()

    if not repo_full or "/" not in repo_full:
        repo_full = input("GitHub 저장소 (예: taewook-3196/RetirementPortfolio): ").strip()
    if not token:
        token = input("GitHub 토큰 (ghp_xxxx...): ").strip()

    owner, repo = repo_full.split("/")
    print(f"\n• 대상 저장소: {owner}/{repo}")

    ctx = ssl._create_unverified_context()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "PortfolioUploader",
    }

    # 1. 대상 파일 수집
    include_dirs = [".github", "core", "data", "database", "portfolio", "services", "strategy", "ui", "scripts", "tests"]
    include_files = ["requirements.txt", ".gitignore", "README.md", "main.py", "build_release.py", "config.yaml", "portfolio.db"]

    files_to_upload = []

    for f in include_files:
        p = project_root / f
        if p.exists() and p.is_file():
            files_to_upload.append(p)

    for d in include_dirs:
        dir_p = project_root / d
        if dir_p.exists():
            for p in dir_p.rglob("*"):
                if p.is_file() and not p.name.endswith(".pyc") and "__pycache__" not in str(p):
                    files_to_upload.append(p)

    # exports/reports 내의 최신 리포트를 index.html로 갱신하여 추가 (GitHub Pages 즉시 오픈용)
    rep_dir = project_root / "exports" / "reports"
    if rep_dir.exists():
        idx_p = rep_dir / "index.html"
        rep_files = sorted([f for f in rep_dir.glob("morning_report_*.html") if f.is_file()])
        if rep_files:
            idx_p.write_text(rep_files[-1].read_text(encoding="utf-8"), encoding="utf-8")
        for h in rep_dir.glob("*.html"):
            if h.is_file() and h not in files_to_upload:
                files_to_upload.append(h)

    print(f"• 업로드할 파일 총 {len(files_to_upload)}개 수집 완료")

    # 2. Blob 생성 (각 파일 업로드)
    print("\n[1/3] 파일 데이터를 GitHub Blobs로 변환 업로드 중...")
    tree_items = []

    for idx, fpath in enumerate(files_to_upload, 1):
        rel_path = fpath.relative_to(project_root).as_posix()
        try:
            content_bytes = fpath.read_bytes()

            # config.yaml 보안 민감 텍스트의 경우 비밀값 비우기
            if fpath.name == "config.yaml":
                import re
                text = content_bytes.decode("utf-8", errors="ignore")
                text = re.sub(r"kakao_access_token: .*", "kakao_access_token: ''", text)
                text = re.sub(r"kakao_refresh_token: .*", "kakao_refresh_token: ''", text)
                text = re.sub(r"kakao_rest_api_key: .*", "kakao_rest_api_key: ''", text)
                text = re.sub(r"github_token: .*", "github_token: ''", text)
                text = re.sub(r"gemini_api_key: .*", "gemini_api_key: ''", text)
                content_bytes = text.encode("utf-8")

            b64_content = base64.b64encode(content_bytes).decode("utf-8")

            blob_url = f"https://api.github.com/repos/{owner}/{repo}/git/blobs"
            blob_data = json.dumps({"content": b64_content, "encoding": "base64"}).encode("utf-8")

            req = urllib.request.Request(blob_url, data=blob_data, headers=headers, method="POST")
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                blob_res = json.loads(resp.read().decode("utf-8"))
                tree_items.append({
                    "path": rel_path,
                    "mode": "100644",
                    "type": "blob",
                    "sha": blob_res["sha"],
                })

            if idx % 5 == 0 or idx == len(files_to_upload):
                print(f"  진행률: ({idx}/{len(files_to_upload)}) {rel_path}", flush=True)
        except Exception as e:
            print(f"  ⚠️ {rel_path} 업로드 오류 (건너뜀): {e}", flush=True)

    # 3. Tree 생성
    print("\n[2/3] GitHub Git Tree 생성 중...")
    tree_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees"
    tree_payload = json.dumps({"tree": tree_items}).encode("utf-8")
    req_tree = urllib.request.Request(tree_url, data=tree_payload, headers=headers, method="POST")
    with urllib.request.urlopen(req_tree, context=ctx, timeout=15) as resp:
        tree_res = json.loads(resp.read().decode("utf-8"))
        tree_sha = tree_res["sha"]

    # 4. Commit 생성
    print("\n[3/3] 메인 브랜치 커밋 및 배포 적용 중...")
    commit_url = f"https://api.github.com/repos/{owner}/{repo}/git/commits"
    commit_payload = json.dumps({
        "message": "Update: Full cloud automation with all modules, multi-account support and mobile Pages",
        "tree": tree_sha,
    }).encode("utf-8")
    req_commit = urllib.request.Request(commit_url, data=commit_payload, headers=headers, method="POST")
    with urllib.request.urlopen(req_commit, context=ctx, timeout=15) as resp:
        commit_res = json.loads(resp.read().decode("utf-8"))
        commit_sha = commit_res["sha"]

    # 5. main Ref 생성 또는 업데이트
    ref_url = f"https://api.github.com/repos/{owner}/{repo}/git/refs"
    ref_payload = json.dumps({
        "ref": "refs/heads/main",
        "sha": commit_sha,
    }).encode("utf-8")

    try:
        req_ref = urllib.request.Request(ref_url, data=ref_payload, headers=headers, method="POST")
        with urllib.request.urlopen(req_ref, context=ctx, timeout=15) as resp:
            print("  main 브랜치 생성 완료!")
    except urllib.error.HTTPError as e:
        # 이미 브랜치가 있는 경우 PATCH로 update
        update_url = f"https://api.github.com/repos/{owner}/{repo}/git/refs/heads/main"
        update_payload = json.dumps({"sha": commit_sha, "force": True}).encode("utf-8")
        req_up = urllib.request.Request(update_url, data=update_payload, headers=headers, method="PATCH")
        with urllib.request.urlopen(req_up, context=ctx, timeout=15) as resp:
            print("  main 브랜치 업데이트 완료!")

    # 6. GitHub Pages 활성화
    try:
        pages_url = f"https://api.github.com/repos/{owner}/{repo}/pages"
        pages_payload = json.dumps({"build_type": "workflow"}).encode("utf-8")
        req_p = urllib.request.Request(pages_url, data=pages_payload, headers=headers, method="POST")
        with urllib.request.urlopen(req_p, context=ctx, timeout=15):
            pass
    except Exception:
        pass

    print("\n" + "=" * 70)
    print("🎉 GitHub 저장소 업로드 및 배포 완료!")
    print("=" * 70)
    print(f"• 저장소 주소: https://github.com/{owner}/{repo}")
    print(f"• 모바일 웹페이지 주소: https://{owner}.github.io/{repo}/")
    print("\n이제 데스크톱 앱에서 [🟢 클라우드 켜기 (ON)]를 누르시면 정상 작동합니다!")


if __name__ == "__main__":
    main()
