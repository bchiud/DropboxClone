"""Unit tests for the Mongo refresh-token repository adapter.

The pymongo collection is a mock. Verifies index setup (unique jti + TTL),
insert, existence check, and delete — the allowlist vocabulary lives here.
"""
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.adapters.mongo_refresh_token_repository import MongoRefreshTokenRepository
from app.models.user import RefreshToken
from app.ports.refresh_token_repository import RefreshTokenRepository


@pytest.fixture
def repo():
    col = MagicMock()
    return MongoRefreshTokenRepository(col), col


def _token(jti: str = "jti-1") -> RefreshToken:
    now = datetime.now(UTC)
    return RefreshToken(
        jti=jti, username="alice",
        created_at=now, expires_at=now + timedelta(days=7),
    )


def test_is_a_refresh_token_repository(repo):
    r, _ = repo
    assert isinstance(r, RefreshTokenRepository)


def test_init_creates_unique_jti_and_ttl_indexes():
    col = MagicMock()
    MongoRefreshTokenRepository(col)
    col.create_index.assert_any_call("jti", unique=True)
    col.create_index.assert_any_call("expires_at", expireAfterSeconds=0)  # TTL


def test_add_inserts_the_dumped_model(repo):
    r, col = repo
    tok = _token()
    r.add(tok)
    col.insert_one.assert_called_once_with(tok.model_dump())


def test_exists_true_when_the_jti_is_present(repo):
    r, col = repo
    col.find_one.return_value = {"jti": "jti-1"}
    assert r.exists("jti-1") is True
    assert col.find_one.call_args.args[0] == {"jti": "jti-1"}


def test_exists_false_when_absent(repo):
    r, col = repo
    col.find_one.return_value = None
    assert r.exists("nope") is False


def test_delete_removes_by_jti(repo):
    r, col = repo
    r.delete("jti-1")
    col.delete_one.assert_called_once_with({"jti": "jti-1"})
