"""Unit tests for the Mongo share-repository adapter."""
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from app.adapters.mongo_share_repository import MongoShareRepository
from app.models.share import Share
from app.ports.share_repository import ShareRepository


@pytest.fixture
def repo():
    col = MagicMock()
    return MongoShareRepository(col), col


def share():
    return Share(owner="bob", path="/x.txt", shared_with="alice", created_at=datetime.now(UTC))


def test_is_a_share_repository(repo):
    r, _ = repo
    assert isinstance(r, ShareRepository)


def test_add_upserts_on_the_triple(repo):
    r, col = repo
    s = share()
    r.add(s)
    kwargs = col.replace_one.call_args.kwargs
    assert kwargs["filter"] == {"owner": "bob", "path": "/x.txt", "shared_with": "alice"}
    assert kwargs["replacement"] == s.model_dump()
    assert kwargs["upsert"] is True


def test_remove_deletes_the_triple(repo):
    r, col = repo
    r.remove("bob", "/x.txt", "alice")
    assert col.delete_one.call_args.kwargs["filter"] == {
        "owner": "bob", "path": "/x.txt", "shared_with": "alice"}


def test_exists_true_and_false(repo):
    r, col = repo
    col.find_one.return_value = {"owner": "bob"}
    assert r.exists("bob", "/x.txt", "alice") is True
    col.find_one.return_value = None
    assert r.exists("bob", "/x.txt", "alice") is False


def test_list_for_recipient_returns_shares_with_projection(repo):
    r, col = repo
    col.find.return_value = iter([share().model_dump()])
    result = r.list_for_recipient("alice")
    assert col.find.call_args.args == ({"shared_with": "alice"}, {"_id": 0})
    assert len(result) == 1
    assert isinstance(result[0], Share)


def test_list_for_owner_returns_shares(repo):
    r, col = repo
    col.find.return_value = iter([share().model_dump()])
    result = r.list_for_owner("bob")
    assert col.find.call_args.args == ({"owner": "bob"}, {"_id": 0})
    assert isinstance(result[0], Share)


def test_remove_all_for_path_deletes_every_grant_on_that_file(repo):
    r, col = repo
    col.delete_many.return_value = MagicMock(deleted_count=3)

    removed = r.remove_all_for_path("bob", "/x.txt")

    # scoped to (owner, path) — NOT the triple: every recipient of this file goes
    assert col.delete_many.call_args.kwargs["filter"] == {"owner": "bob", "path": "/x.txt"}
    assert removed == 3


def test_remove_all_for_path_reports_zero_when_nothing_matched(repo):
    r, col = repo
    col.delete_many.return_value = MagicMock(deleted_count=0)
    assert r.remove_all_for_path("bob", "/never-shared.txt") == 0
