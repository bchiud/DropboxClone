"""Route tests for the auth endpoints.

The AuthService dependency is overridden with a fake, so routes are tested
in isolation from Mongo / bcrypt. Verifies wiring, error translation, and
that the password hash is never exposed.
"""
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.application.auth_service import (
    InvalidCredentials,
    InvalidRefreshToken,
    UsernameTaken,
)
from app.dependencies import get_auth_service
from app.main import app
from app.models.user import User


class FakeAuthService:
    logged_out = None

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
            return "a.jwt.token", "r.jwt.token"  # (access, refresh)
        raise InvalidCredentials()

    def refresh(self, refresh_token):
        if refresh_token == "valid.refresh":
            return "new.access.token"
        raise InvalidRefreshToken()

    def logout(self, refresh_token):
        self.logged_out = refresh_token


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


# --- login issues both tokens ---

def test_login_returns_access_and_refresh_tokens(client):
    resp = client.post("/auth/login", data={"username": "alice", "password": "correct"})
    assert resp.status_code == 200
    assert resp.json() == {
        "access_token": "a.jwt.token",
        "refresh_token": "r.jwt.token",
        "token_type": "bearer",
    }


def test_login_wrong_credentials_returns_401(client):
    resp = client.post("/auth/login", data={"username": "alice", "password": "wrong"})
    assert resp.status_code == 401


# --- refresh ---

def test_refresh_returns_only_a_new_access_token(client):
    resp = client.post("/auth/refresh", json={"refresh_token": "valid.refresh"})
    assert resp.status_code == 200
    assert resp.json() == {"access_token": "new.access.token", "token_type": "bearer"}
    assert "refresh_token" not in resp.json()  # /refresh does not re-issue a refresh token


def test_refresh_invalid_token_returns_401(client):
    resp = client.post("/auth/refresh", json={"refresh_token": "bad"})
    assert resp.status_code == 401


# --- logout ---

def test_logout_returns_204(client):
    resp = client.post("/auth/logout", json={"refresh_token": "whatever"})
    assert resp.status_code == 204
    assert resp.content == b""


def test_logout_passes_the_token_to_the_service():
    fake = FakeAuthService()
    app.dependency_overrides[get_auth_service] = lambda: fake
    try:
        resp = TestClient(app).post("/auth/logout", json={"refresh_token": "r1"})
        assert resp.status_code == 204
        assert fake.logged_out == "r1"
    finally:
        app.dependency_overrides.clear()
