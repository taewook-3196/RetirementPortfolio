from uuid import uuid4

import pytest

from services.kakao_delivery_authenticated_recovery import preflight_for_authenticated_operator


def test_authenticated_admin_identity_passed_to_preflight(monkeypatch):
    from web import app as web_app
    from services import kakao_delivery_authenticated_recovery as subject

    actor = uuid4()
    monkeypatch.setattr(web_app, "require_admin", lambda authorization: {"user_id": str(actor)})
    captured = {}

    def fake_preflight(engine, **kwargs):
        captured.update(kwargs)
        return "checked"

    monkeypatch.setattr(subject, "check_recovery_audit_preflight", fake_preflight)
    assert preflight_for_authenticated_operator(object(), authorization="Bearer test", record="record") == "checked"
    assert captured["authenticated_actor_id"] == actor
    assert captured["resolve_admin"](actor) is True
    assert captured["resolve_admin"](uuid4()) is False


def test_unauthorized_session_never_reaches_database(monkeypatch):
    from fastapi import HTTPException
    from web import app as web_app
    from services import kakao_delivery_authenticated_recovery as subject

    def reject(_authorization):
        raise HTTPException(status_code=403, detail="forbidden")

    monkeypatch.setattr(web_app, "require_admin", reject)
    monkeypatch.setattr(subject, "check_recovery_audit_preflight",
                        lambda *args, **kwargs: pytest.fail("DB preflight must not run"))
    with pytest.raises(HTTPException) as exc:
        preflight_for_authenticated_operator(object(), authorization="Bearer invalid", record=None)
    assert exc.value.status_code == 403
