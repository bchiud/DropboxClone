"""Unit tests for the web-layer auth dependency."""
import pytest
from fastapi import HTTPException

from app.auth_dependencies import get_current_user
from app.domain import security


def test_valid_token_returns_username():
    token = security.create_access_token("alice")
    assert get_current_user(token=token) == "alice"


def test_invalid_token_raises_401():
    with pytest.raises(HTTPException) as exc:
        get_current_user(token="garbage.token")
    assert exc.value.status_code == 401


def test_expired_token_raises_401(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "access_token_expire_minutes", -1)
    token = security.create_access_token("bob")
    with pytest.raises(HTTPException) as exc:
        get_current_user(token=token)
    assert exc.value.status_code == 401
