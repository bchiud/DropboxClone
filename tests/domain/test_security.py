"""Unit tests for security primitives — hashing and JWTs."""
from datetime import UTC, datetime, timedelta

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


# --- refresh tokens ---

def test_refresh_token_round_trip_returns_subject_and_jti():
    token = security.create_refresh_token("alice", "jti-r1", _future())
    assert security.decode_refresh_token(token) == ("alice", "jti-r1")


def test_expired_refresh_token_returns_none():
    past = datetime.now(UTC) - timedelta(minutes=1)
    token = security.create_refresh_token("alice", "jti-r1", past)
    assert security.decode_refresh_token(token) is None


def test_refresh_token_is_rejected_by_access_decoder():
    # the confusion hole: a refresh token must NOT authenticate as an access token
    token = security.create_refresh_token("alice", "jti-r1", _future())
    assert security.decode_access_token(token) is None


def test_access_token_is_rejected_by_refresh_decoder():
    token = security.create_access_token("alice")
    assert security.decode_refresh_token(token) is None


def test_share_token_is_rejected_by_refresh_decoder():
    token = security.create_share_token("bob", "/x.txt", "jti-1", _future())
    assert security.decode_refresh_token(token) is None


def test_garbage_refresh_token_returns_none():
    assert security.decode_refresh_token("not.a.jwt") is None


# --- share-link tokens ---

def _future():
    return datetime.now(UTC) + timedelta(minutes=60)


def test_share_token_round_trip_returns_owner_path_and_jti():
    token = security.create_share_token("bob", "/x.txt", "jti-1", _future())
    assert security.decode_share_token(token) == ("bob", "/x.txt", "jti-1")


def test_expired_share_token_returns_none():
    past = datetime.now(UTC) - timedelta(minutes=1)
    token = security.create_share_token("bob", "/x.txt", "jti-1", past)
    assert security.decode_share_token(token) is None


def test_access_token_is_rejected_by_share_decoder():
    # same secret, but the missing typ="share" claim must not be readable as a link
    token = security.create_access_token("bob")
    assert security.decode_share_token(token) is None


def test_forged_share_token_with_wrong_secret_returns_none():
    forged = jwt.encode(
        {"typ": "share", "owner": "mallory", "path": "/x.txt"},
        "not-the-secret", algorithm="HS256")
    assert security.decode_share_token(forged) is None


def test_garbage_share_token_returns_none():
    assert security.decode_share_token("not.a.jwt") is None
