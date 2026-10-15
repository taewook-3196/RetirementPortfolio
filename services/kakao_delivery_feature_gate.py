"""Opt-in gate for the staged Kakao delivery-state sender.

This module does not activate or call the sender. Production continues using
its existing delivery path until an explicitly reviewed cutover.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class DeliveryFeatureGate:
    enabled: bool
    reason: str


def evaluate_delivery_feature_gate(env=None) -> DeliveryFeatureGate:
    """Fail closed unless both explicit, exact opt-in values are present.

    This is deliberately not a permissive truthy parser: typos, whitespace,
    missing configuration, or partial rollout configuration all disable it.
    """
    values = os.environ if env is None else env
    if values.get("KAKAO_DELIVERY_STATE_ENABLED") != "true":
        return DeliveryFeatureGate(False, "delivery state feature is disabled")
    if values.get("KAKAO_DELIVERY_CUTOVER_APPROVED") != "true":
        return DeliveryFeatureGate(False, "cutover has not been approved")
    return DeliveryFeatureGate(True, "explicit delivery state cutover opt-in")
