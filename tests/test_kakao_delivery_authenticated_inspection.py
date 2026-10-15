from uuid import uuid4

import pytest

from services.kakao_delivery_authenticated_inspection import inspect_for_authenticated_operator


def test_verified_session_identity_is_used_not_client_target(monkeypatch):
    from web import app as web_app
    from services import kakao_delivery_authenticated_inspection as subject

    actor = uuid4()
    monkeypatch.setattr(web_app, "require_admin", lambda authorization: {"user_id": str(actor)})
    captured = {}

    def fake_inspect(engine, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(subject, "inspect_for_operator", fake_inspect)
    assert inspect_for_authenticated_operator(object(), authorization="Bearer test", limit=10) == []
    assert captured == {"actor_id": actor, "actor_is_admin": True, "target_user_id": actor, "limit": 10}


def test_authentication_error_propagates_without_inspection(monkeypatch):
    from fastapi import HTTPException
    from web import app as web_app
    from services import kakao_delivery_authenticated_inspection as subject

    def reject(_authorization):
        raise HTTPException(status_code=403, detail="forbidden")

    monkeypatch.setattr(web_app, "require_admin", reject)
    monkeypatch.setattr(subject, "inspect_for_operator", lambda *args, **kwargs: pytest.fail("DB inspection must not run"))
    with pytest.raises(HTTPException) as exc:
        inspect_for_authenticated_operator(object(), authorization="Bearer invalid")
    assert exc.value.status_code == 403
