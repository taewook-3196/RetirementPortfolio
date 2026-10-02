"""Create a one-time signup invitation and print its secret exactly once."""

from __future__ import annotations

import argparse
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from database.connection import get_db_session
from database.models import InviteCode


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", default="", help="Optional allowed signup email")
    parser.add_argument("--label", default="", help="Human-readable recipient label")
    parser.add_argument("--days", type=int, default=7, help="Validity period in days")
    args = parser.parse_args()

    if args.days < 1 or args.days > 365:
        raise SystemExit("--days must be between 1 and 365")

    code = secrets.token_urlsafe(24)
    digest = hashlib.sha256(code.encode("utf-8")).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(days=args.days)

    with get_db_session() as db:
        db.add(
            InviteCode(
                code_hash=digest,
                label=args.label.strip() or None,
                intended_email=args.email.strip().lower() or None,
                expires_at=expires_at,
            )
        )

    print("Invite created. Share this secret once; it cannot be recovered later:")
    print(code)
    print(f"Expires: {expires_at.isoformat()}")


if __name__ == "__main__":
    main()
