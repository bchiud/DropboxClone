"""Unit tests for the Mongo file-repository adapter.

The pymongo collection is injected as a mock. All Mongo query vocabulary
(filters, projections, upsert) and the model <-> dict translation live in
this adapter and are verified here.
"""
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from app.adapters.mongo_file_repository import MongoFileRepository
from app.models.file import FileRecord, FileSummary
from app.ports.file_repository import FileRepository


@pytest.fixture
def repo():
    col = MagicMock()
    return MongoFileRepository(col), col


def test_is_a_file_repository(repo):
    r, _ = repo
    assert isinstance(r, FileRepository)


def test_save_dumps_model_and_upserts_with_identity_filter(repo):
    r, col = repo
    record = FileRecord(
        owner="u", path="/a.txt", size=5,
        block_hashes=["h"], updated_at=datetime.now(UTC),
    )
    r.save(record)
    kwargs = col.replace_one.call_args.kwargs
    assert kwargs["filter"] == {"owner": "u", "path": "/a.txt"}
    assert kwargs["replacement"] == record.model_dump()  # model -> dict
    assert kwargs["upsert"] is True


def test_get_returns_file_record(repo):
    r, col = repo
    col.find_one.return_value = {
        "owner": "u", "path": "/a.txt", "size": 5,
        "block_hashes": ["h1"], "updated_at": datetime.now(UTC),
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


def test_list_for_owner_projects_and_returns_summaries(repo):
    r, col = repo
    col.find.return_value = iter([
        {"owner": "u", "path": "/a.txt", "size": 5, "updated_at": datetime.now(UTC)},
    ])
    result = r.list_for_owner("u")
    args = col.find.call_args.args
    assert args[0] == {"owner": "u"}
    assert args[1] == {"_id": 0, "block_hashes": 0}
    assert len(result) == 1
    assert isinstance(result[0], FileSummary)
    assert result[0].path == "/a.txt"
