"""Server-side encryption helpers for per-user OAuth credentials."""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken


def _fernet() -> Fernet:
    secret = os.getenv("OAUTH_TOKEN_ENCRYPTION_KEY", "").strip()
    if not secret:
        raise RuntimeError("OAUTH_TOKEN_ENCRYPTION_KEY 환경변수가 필요합니다.")

    # Accept a high-entropy application secret and deterministically derive the
    # 32-byte Fernet key. The original secret never goes into the database.
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    clean = str(value or "")
    if not clean:
        raise ValueError("암호화할 비밀값이 비어 있습니다.")
    return _fernet().encrypt(clean.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str) -> str:
    try:
        return _fernet().decrypt(str(value).encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("저장된 OAuth 토큰을 복호화할 수 없습니다.") from exc
