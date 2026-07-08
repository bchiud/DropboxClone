"""Route tests for the auth endpoints.

The AuthService dependency is overridden with a fake, so routes are tested
in isolation from Mongo / bcrypt. Verifies wiring, error translation, and
that the password hash is never exposed.
"""
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.application.auth_service import InvalidCredentials, UsernameTaken
from app.dependencies import get_auth_service
from app.main import app
from app.models.user import User


class FakeAuthService:
    def register(self, username, password):
        if username == "taken":
            raise UsernameTaken(username)
        return User(
            username=username,
            password_hash="HASH_MUST_NOT_LEAK",
            created_at=datetime.now(UTC),
        )

    def authenticate(self, username, password):
        if password == "correct":
            return "a.jwt.token"
        raise InvalidCredentials()


@pytest.fixture
def client():
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_register_returns_201_and_safe_fields(client):
    resp = client.post("/auth/register", json={"username": "alice", "password": "pw"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["username"] == "alice"
    assert "created_at" in body


def test_register_never_leaks_password_hash(client):
    # Regression guard: the bcrypt hash must never appear in a response.
    resp = client.post("/auth/register", json={"username": "alice", "password": "pw"})
    assert "password_hash" not in resp.json()
    assert "HASH_MUST_NOT_LEAK" not in resp.text


def test_register_duplicate_returns_409(client):
    resp = client.post("/auth/register", json={"username": "taken", "password": "pw"})
    assert resp.status_code == 409


def test_login_returns_bearer_token(client):
    resp = client.post("/auth/login", data={"username": "alice", "password": "correct"})
    assert resp.status_code == 200
    assert resp.json() == {"access_token": "a.jwt.token", "token_type": "bearer"}


def test_login_wrong_credentials_returns_401(client):
    resp = client.post("/auth/login", data={"username": "alice", "password": "wrong"})
    assert resp.status_code == 401
