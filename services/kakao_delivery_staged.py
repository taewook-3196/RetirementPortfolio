"""Staged wiring for delivery claims and a caller-supplied Kakao transport.

NOT imported by the production scheduler. No Kakao API credentials are read.
The caller is responsible for using a trusted backend DB engine and for
supplying an appropriately configured transport only after approved cutover.
"""

from uuid import uuid4

from services.kakao_delivery_orchestrator import send_with_delivery_claim
from services.kakao_delivery_postgres import DeliveryAttempt, PostgresDeliveryAttempts


def run_staged_delivery(*, engine, user_id, report_date, transport, env=None):
    """Claim durably before invoking transport; fail closed on DB exceptions.

    Each invocation gets a unique attempt ID. If a prior attempt is ambiguous,
    the database's active-attempt constraint prevents automatic redelivery.
    """
    attempt = DeliveryAttempt(user_id=user_id, report_date=report_date, attempt_id=uuid4())
    store = PostgresDeliveryAttempts(engine)
    return send_with_delivery_claim(
        claim=lambda: store.claim(attempt),
        transport=transport,
        finish=lambda status: (store.finish_sent_with_legacy(attempt) if status == "sent" else store.finish(attempt, status)),
        env=env,
    )
