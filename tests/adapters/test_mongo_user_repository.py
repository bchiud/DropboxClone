"""Unit tests for the Mongo user-repository adapter.

The pymongo collection is injected as a mock; the adapter translates
between the User model and Mongo dicts.
"""
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from app.adapters.mongo_user_repository import MongoUserRepository
from app.models.user import User
from app.ports.user_repository import UserRepository


@pytest.fixture
def repo():
    col = MagicMock()
    return MongoUserRepository(col), col


def test_is_a_user_repository(repo):
    r, _ = repo
    assert isinstance(r, UserRepository)


def test_get_by_username_returns_user(repo):
    r, col = repo
    col.find_one.return_value = {
        "username": "alice", "password_hash": "h",
        "created_at": datetime.now(UTC), "_id": "ignored",
    }
    got = r.get_by_username("alice")
    assert isinstance(got, User)
    assert got.username == "alice"
    assert got.password_hash == "h"


def test_get_by_username_returns_none_when_missing(repo):
    r, col = repo
    col.find_one.return_value = None
    assert r.get_by_username("nobody") is None


def test_save_dumps_model_and_upserts_with_username_filter(repo):
    r, col = repo
    user = User(username="bob", password_hash="h", created_at=datetime.now(UTC))
    r.save(user)
    kwargs = col.replace_one.call_args.kwargs
    assert kwargs["filter"] == {"username": "bob"}
    assert kwargs["replacement"] == user.model_dump()
    assert kwargs["upsert"] is True
