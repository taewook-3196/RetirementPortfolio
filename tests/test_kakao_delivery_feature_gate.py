from services.kakao_delivery_feature_gate import evaluate_delivery_feature_gate


def test_gate_defaults_off():
    assert not evaluate_delivery_feature_gate({}).enabled


def test_gate_rejects_partial_approval():
    assert not evaluate_delivery_feature_gate({"KAKAO_DELIVERY_STATE_ENABLED": "true"}).enabled
    assert not evaluate_delivery_feature_gate({"KAKAO_DELIVERY_CUTOVER_APPROVED": "true"}).enabled


def test_gate_rejects_typos_and_truthy_values():
    for value in ("TRUE", "1", "yes", "true ", ""):
        assert not evaluate_delivery_feature_gate({
            "KAKAO_DELIVERY_STATE_ENABLED": value,
            "KAKAO_DELIVERY_CUTOVER_APPROVED": "true",
        }).enabled


def test_gate_requires_two_explicit_approvals():
    assert evaluate_delivery_feature_gate({
        "KAKAO_DELIVERY_STATE_ENABLED": "true",
        "KAKAO_DELIVERY_CUTOVER_APPROVED": "true",
    }).enabled
