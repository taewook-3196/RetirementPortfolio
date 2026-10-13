"""Atomic local deduplication for independently hosted administrator alerts.

The caller must supply a durable, private directory shared by successive
watchdog runs. This module never sends messages or accesses production data.
"""
from __future__ import annotations

import os
from pathlib import Path
import re

_KEY_PATTERN = re.compile(r"^[0-9a-f]{24}$")


def claim_alert(key: str, directory: str | Path) -> bool:
    """Atomically claim an alert key; return False if already claimed.

    Raises on storage errors. A successful claim must be followed by an
    outbound notification; callers must handle send failure and recovery.
    """
    if not _KEY_PATTERN.fullmatch(key):
        raise ValueError("invalid alert deduplication key")
    root = Path(directory)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = root / (key + ".claim")
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(key + "\n")
    return True


def release_alert(key: str, directory: str | Path) -> None:
    """Release a claim after a verified send failure to allow later retry."""
    if not _KEY_PATTERN.fullmatch(key):
        raise ValueError("invalid alert deduplication key")
    (Path(directory) / (key + ".claim")).unlink(missing_ok=True)
