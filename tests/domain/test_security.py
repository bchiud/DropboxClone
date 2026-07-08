"""Unit tests for security primitives — hashing and JWTs."""
import jwt

from app.config import settings
from app.domain import security


def test_hash_is_not_plaintext():
    h = security.hash_password("hunter2")
    assert h != "hunter2"


def test_verify_correct_and_wrong_password():
    h = security.hash_password("hunter2")
    assert security.verify_password("hunter2", h) is True
    assert security.verify_password("nope", h) is False


def test_same_password_hashes_differently():
    # random salt -> different hash each time
    assert security.hash_password("pw") != security.hash_password("pw")


def test_token_round_trip_returns_subject():
    token = security.create_access_token("alice")
    assert security.decode_access_token(token) == "alice"


def test_tampered_token_returns_none():
    token = security.create_access_token("alice")
    assert security.decode_access_token(token + "x") is None


def test_forged_token_with_wrong_secret_returns_none():
    forged = jwt.encode({"sub": "mallory"}, "not-the-secret", algorithm="HS256")
    assert security.decode_access_token(forged) is None


def test_expired_token_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "access_token_expire_minutes", -1)  # already expired
    token = security.create_access_token("bob")
    assert security.decode_access_token(token) is None


def test_garbage_token_returns_none():
    assert security.decode_access_token("not.a.jwt") is None
