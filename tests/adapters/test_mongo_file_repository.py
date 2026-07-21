"""Unit tests for the Mongo file-repository adapter.

The pymongo collection is injected as a mock. All Mongo query vocabulary
(filters, projections, upsert) and the model <-> dict translation live in
this adapter and are verified here.
"""
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from pymongo.errors import DuplicateKeyError

from app.adapters.mongo_file_repository import MongoFileRepository
from app.domain.recipe import recipe_etag
from app.models.file import FileRecord, FileSummary
from app.ports.file_repository import FileRepository, VersionConflict


def _record(block_hashes=("h",)):
    bh = list(block_hashes)
    return FileRecord(
        owner="u", path="/a.txt", size=5,
        block_hashes=bh, updated_at=datetime.now(UTC), etag=recipe_etag(bh),
    )


@pytest.fixture
def repo():
    col = MagicMock()
    return MongoFileRepository(col), col


def test_is_a_file_repository(repo):
    r, _ = repo
    assert isinstance(r, FileRepository)


def test_create_inserts_the_record(repo):
    # expected_etag=None means "I believe this is new" -> plain insert
    r, col = repo
    record = _record()
    r.save(record, expected_etag=None)
    col.insert_one.assert_called_once_with(record.model_dump())
    col.replace_one.assert_not_called()


def test_create_on_duplicate_with_same_content_is_idempotent(repo):
    # a retried/concurrent create of identical content is swallowed, not raised
    r, col = repo
    record = _record()
    col.insert_one.side_effect = DuplicateKeyError("dup")
    col.find_one.return_value = {"etag": record.etag}
    r.save(record, expected_etag=None)  # no raise


def test_create_on_duplicate_with_different_content_conflicts(repo):
    r, col = repo
    record = _record()
    col.insert_one.side_effect = DuplicateKeyError("dup")
    col.find_one.return_value = {"etag": "someone-elses-etag"}
    with pytest.raises(VersionConflict):
        r.save(record, expected_etag=None)


def test_update_uses_conditional_cas_filter(repo):
    # the precondition: replace only if current etag is the base I read OR already
    # the target (the retry/parallel-write fold), and never upsert.
    r, col = repo
    record = _record(["h1", "h2"])
    col.replace_one.return_value = MagicMock(matched_count=1)
    r.save(record, expected_etag="base-etag")
    kwargs = col.replace_one.call_args.kwargs
    assert kwargs["filter"] == {
        "owner": "u", "path": "/a.txt",
        "etag": {"$in": ["base-etag", record.etag]},
    }
    assert kwargs["replacement"] == record.model_dump()
    assert kwargs["upsert"] is False


def test_update_raises_when_precondition_matches_nothing(repo):
    r, col = repo
    col.replace_one.return_value = MagicMock(matched_count=0)
    with pytest.raises(VersionConflict):
        r.save(_record(), expected_etag="stale-etag")


def test_get_returns_file_record(repo):
    r, col = repo
    col.find_one.return_value = {
        "owner": "u", "path": "/a.txt", "size": 5,
        "block_hashes": ["h1"], "updated_at": datetime.now(UTC),
        "etag": recipe_etag(["h1"]),
        "_id": "ignored-by-pydantic",
    }
    got = r.get("u", "/a.txt")
    assert isinstance(got, FileRecord)
    assert got.block_hashes == ["h1"]  # full record, recipe intact


def test_get_returns_none_when_missing_without_raising(repo):
    # Policy decision (raise 404) belongs to the service, not the repo.
    r, col = repo
    col.find_one.return_value = None
    assert r.get("u", "/missing") is None


def test_delete_returns_true_when_a_doc_was_removed(repo):
    r, col = repo
    col.delete_one.return_value = MagicMock(deleted_count=1)
    assert r.delete("u", "/a.txt") is True
    assert col.delete_one.call_args.kwargs["filter"] == {"owner": "u", "path": "/a.txt"}


def test_delete_returns_false_when_nothing_matched(repo):
    # owner scoping: a filter that matches no doc (wrong owner, or already gone)
    # removes nothing and reports False, which the service turns into a 404.
    r, col = repo
    col.delete_one.return_value = MagicMock(deleted_count=0)
    assert r.delete("u", "/missing") is False


def test_list_for_owner_projects_and_returns_summaries(repo):
    r, col = repo
    col.find.return_value = iter([
        {"owner": "u", "path": "/a.txt", "size": 5,
         "updated_at": datetime.now(UTC), "etag": recipe_etag(["h"])},
    ])
    result = r.list_for_owner("u")
    args = col.find.call_args.args
    assert args[0] == {"owner": "u"}
    assert args[1] == {"_id": 0, "block_hashes": 0}
    assert len(result) == 1
    assert isinstance(result[0], FileSummary)
    assert result[0].path == "/a.txt"


def test_init_creates_the_unique_identity_index(repo):
    _, col = repo
    # (owner, path) is the file's identity: it's save()'s upsert filter and the
    # filter get() and delete() query on. unique=True makes the database enforce
    # what the upsert already assumes — one recipe per path per owner.
    col.create_index.assert_called_once_with(
        [("owner", 1), ("path", 1)], unique=True
    )


def test_the_identity_index_is_not_unique_on_owner_alone(repo):
    """A unique index on `owner` would allow one file per user, and would fail to
    build against any collection where someone owns two files."""
    _, col = repo
    keys, kwargs = col.create_index.call_args.args[0], col.create_index.call_args.kwargs
    assert [k for k, _ in keys] == ["owner", "path"]
    assert kwargs.get("unique") is True
