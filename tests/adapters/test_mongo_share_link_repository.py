"""Unit tests for the Mongo share-link-repository adapter."""
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.adapters.mongo_share_link_repository import MongoShareLinkRepository
from app.models.share import ShareLink
from app.ports.share_link_repository import ShareLinkRepository


@pytest.fixture
def repo():
    col = MagicMock()
    return MongoShareLinkRepository(col), col


def link():
    exp = datetime.now(UTC) + timedelta(minutes=10080)
    return ShareLink(jti="j1", owner="bob", path="/x.txt", expires_at=exp)


def test_is_a_share_link_repository(repo):
    r, _ = repo
    assert isinstance(r, ShareLinkRepository)


def test_add_inserts_the_dumped_doc(repo):
    r, col = repo
    ln = link()
    r.add(ln)
    assert col.insert_one.call_args.args[0] == ln.model_dump()


def test_delete_is_owner_scoped(repo):
    r, col = repo
    r.delete("bob", "j1")
    assert col.delete_one.call_args.args[0] == {"owner": "bob", "jti": "j1"}


def test_exists_true_and_false(repo):
    r, col = repo
    col.find_one.return_value = {"jti": "j1"}
    assert r.exists("j1") is True
    col.find_one.return_value = None
    assert r.exists("j1") is False


def test_list_for_owner_projects_id_and_rebuilds_links(repo):
    r, col = repo
    col.find.return_value = iter([link().model_dump()])
    result = r.list_for_owner("bob")
    assert col.find.call_args.args == ({"owner": "bob"}, {"_id": 0})
    assert len(result) == 1
    assert isinstance(result[0], ShareLink)


def test_delete_all_for_path_deletes_every_link_on_that_file(repo):
    r, col = repo
    col.delete_many.return_value = MagicMock(deleted_count=2)

    deleted = r.delete_all_for_path("bob", "/x.txt")

    assert col.delete_many.call_args.args[0] == {"owner": "bob", "path": "/x.txt"}
    assert deleted == 2


def test_delete_all_for_path_reports_zero_when_nothing_matched(repo):
    r, col = repo
    col.delete_many.return_value = MagicMock(deleted_count=0)
    assert r.delete_all_for_path("bob", "/never-linked.txt") == 0


def test_init_creates_the_link_indexes(repo):
    _, col = repo
    col.create_index.assert_any_call("jti", unique=True)   # exists() / delete()
    col.create_index.assert_any_call([("owner", 1), ("path", 1)])  # delete_all_for_path
    col.create_index.assert_any_call("expires_at", expireAfterSeconds=0)  # TTL auto-reap


def test_add_stores_expires_at_as_a_datetime(repo):
    """Mongo's TTL reaper only fires on BSON Dates. A model_dump(mode="json") here
    would serialise expires_at to a string, and the reaper would silently do nothing."""
    r, col = repo
    r.add(link())
    assert isinstance(col.insert_one.call_args.args[0]["expires_at"], datetime)
