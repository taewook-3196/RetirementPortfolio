"""
services/github_service.py
GitHub REST API 연동 서비스.
- GitHub Actions 워크플로우 상태 조회 (GET /repos/{owner}/{repo}/actions/workflows/{id})
- 워크플로우 원격 활성화 (PUT /repos/{owner}/{repo}/actions/workflows/{id}/enable)
- 워크플로우 원격 비활성화 (PUT /repos/{owner}/{repo}/actions/workflows/{id}/disable)
- 워크플로우 원격 즉시 실행 (POST /repos/{owner}/{repo}/actions/workflows/{id}/dispatches)
"""

from __future__ import annotations
import json
import logging
import urllib.request
import urllib.parse
import ssl
from typing import Dict, Any, Optional, Tuple
from core.config import AppConfig, MorningReportConfig, save_config

logger = logging.getLogger("RetirementPortfolio.GitHubService")


class GitHubService:
    """GitHub Actions REST API 원격 제어 클라이언트"""

    API_BASE = "https://api.github.com"

    def __init__(self, config: AppConfig):
        self.config = config
        self.ssl_context = ssl._create_unverified_context()

    @property
    def morning_cfg(self) -> MorningReportConfig:
        return getattr(self.config, "morning_report", MorningReportConfig())

    def _get_headers(self) -> Dict[str, str]:
        token = self.morning_cfg.github_token.strip()
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "RetirementPortfolio-DesktopApp",
        }

    @property
    def clean_repo(self) -> str:
        repo = self.morning_cfg.github_repo.strip()
        if "github.com/" in repo:
            repo = repo.split("github.com/")[1]
        return repo.strip("/").removesuffix(".git")

    def is_configured(self) -> bool:
        """저장소 정보 및 토큰 설정 여부 확인"""
        cfg = self.morning_cfg
        return bool(self.clean_repo and cfg.github_token.strip())

    def get_workflow_status(self) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        GitHub Actions 워크플로우의 현재 상태(active, disabled_manually 등)를 조회합니다.
        반환값: (성공 여부, 메시지/상태텍스트, 워크플로우 상세정보 dict)
        """
        if not self.is_configured():
            return False, "저장소(owner/repo) 및 GitHub 토큰이 설정되지 않았습니다.", None

        repo = self.clean_repo
        workflow_id = self.morning_cfg.github_workflow_id.strip() or "morning_report.yml"
        url = f"{self.API_BASE}/repos/{repo}/actions/workflows/{workflow_id}"

        req = urllib.request.Request(url, headers=self._get_headers(), method="GET")

        try:
            with urllib.request.urlopen(req, context=self.ssl_context, timeout=10) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    state = data.get("state", "unknown")
                    # active, disabled_manually, disabled_inactivity
                    is_active = (state == "active")
                    self.morning_cfg.github_cloud_enabled = is_active
                    save_config(self.config)

                    desc = "활성화 (매일 07:00 실행 대기 중)" if is_active else "비활성화 (중지 상태)"
                    return True, desc, data
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="ignore")
            logger.error(f"GitHub 워크플로우 상태 조회 실패 (HTTP {e.code}): {err}")
            return False, f"HTTP {e.code}: {err}", None
        except Exception as e:
            logger.error(f"GitHub 워크플로우 상태 조회 예외: {e}")
            return False, str(e), None

        return False, "상태를 확인할 수 없습니다.", None

    def enable_workflow(self) -> Tuple[bool, str]:
        """
        GitHub Actions 워크플로우를 원격으로 활성화(Enable)합니다.
        (매일 07:00 스케줄 자동 실행이 켜집니다)
        """
        if not self.is_configured():
            return False, "저장소(owner/repo) 및 GitHub 토큰이 설정되지 않았습니다."

        repo = self.clean_repo
        workflow_id = self.morning_cfg.github_workflow_id.strip() or "morning_report.yml"
        url = f"{self.API_BASE}/repos/{repo}/actions/workflows/{workflow_id}/enable"

        req = urllib.request.Request(url, headers=self._get_headers(), method="PUT")

        try:
            with urllib.request.urlopen(req, context=self.ssl_context, timeout=10) as resp:
                if resp.status in (200, 204):
                    self.morning_cfg.github_cloud_enabled = True
                    save_config(self.config)
                    logger.info(f"GitHub 워크플로우 활성화 성공: {repo}/{workflow_id}")
                    return True, "클라우드 모닝 리포트가 성공적으로 활성화되었습니다! (매일 아침 07:00 자동 발송)"
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="ignore")
            logger.error(f"GitHub 워크플로우 활성화 실패 (HTTP {e.code}): {err}")
            return False, f"활성화 실패 (HTTP {e.code}): {err}"
        except Exception as e:
            logger.error(f"GitHub 워크플로우 활성화 예외: {e}")
            return False, str(e)

        return False, "알 수 없는 오류로 활성화되지 않았습니다."

    def disable_workflow(self) -> Tuple[bool, str]:
        """
        GitHub Actions 워크플로우를 원격으로 비활성화(Disable)합니다.
        (클라우드 자동 실행이 완전 중단됩니다)
        """
        if not self.is_configured():
            return False, "저장소(owner/repo) 및 GitHub 토큰이 설정되지 않았습니다."

        repo = self.clean_repo
        workflow_id = self.morning_cfg.github_workflow_id.strip() or "morning_report.yml"
        url = f"{self.API_BASE}/repos/{repo}/actions/workflows/{workflow_id}/disable"

        req = urllib.request.Request(url, headers=self._get_headers(), method="PUT")

        try:
            with urllib.request.urlopen(req, context=self.ssl_context, timeout=10) as resp:
                if resp.status in (200, 204):
                    self.morning_cfg.github_cloud_enabled = False
                    save_config(self.config)
                    logger.info(f"GitHub 워크플로우 비활성화 성공: {repo}/{workflow_id}")
                    return True, "클라우드 모닝 리포트가 비활성화되었습니다. (자동 발송 중단)"
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="ignore")
            logger.error(f"GitHub 워크플로우 비활성화 실패 (HTTP {e.code}): {err}")
            return False, f"비활성화 실패 (HTTP {e.code}): {err}"
        except Exception as e:
            logger.error(f"GitHub 워크플로우 비활성화 예외: {e}")
            return False, str(e)

        return False, "알 수 없는 오류로 비활성화되지 않았습니다."

    def trigger_workflow_dispatch(self, branch: str = "main") -> Tuple[bool, str]:
        """
        GitHub Actions에 즉시 실행 신호(workflow_dispatch)를 전송하여
        클라우드 서버에서 지금 바로 모닝 리포트를 실행 및 발송하도록 합니다.
        """
        if not self.is_configured():
            return False, "저장소(owner/repo) 및 GitHub 토큰이 설정되지 않았습니다."

        repo = self.clean_repo
        workflow_id = self.morning_cfg.github_workflow_id.strip() or "morning_report.yml"
        url = f"{self.API_BASE}/repos/{repo}/actions/workflows/{workflow_id}/dispatches"

        payload = json.dumps({"ref": branch}).encode("utf-8")
        headers = self._get_headers()
        headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, context=self.ssl_context, timeout=10) as resp:
                if resp.status in (200, 204):
                    logger.info(f"GitHub 워크플로우 즉시 실행 신호 전송 완료: {repo}/{workflow_id}")
                    return True, "GitHub 클라우드 서버에 즉시 실행 신호를 전송했습니다! 잠시 후 카카오톡 메시지가 도착합니다."
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="ignore")
            logger.error(f"GitHub 워크플로우 실행 트리거 실패 (HTTP {e.code}): {err}")
            return False, f"트리거 실패 (HTTP {e.code}): {err}"
        except Exception as e:
            logger.error(f"GitHub 워크플로우 실행 트리거 예외: {e}")
            return False, str(e)

        return False, "알 수 없는 오류로 실행 신호가 전송되지 않았습니다."
