"""Unit tests for the Mongo file-repository adapter.

The pymongo collection is injected as a mock. All Mongo query vocabulary
(filters, projections, upsert) lives in this adapter and is verified here.
"""
from unittest.mock import MagicMock

import pytest

from app.adapters.mongo_file_repository import MongoFileRepository
from app.ports.file_repository import FileRepository


@pytest.fixture
def repo():
    col = MagicMock()
    return MongoFileRepository(col), col


def test_is_a_file_repository(repo):
    r, _ = repo
    assert isinstance(r, FileRepository)


def test_save_upserts_with_identity_filter(repo):
    r, col = repo
    doc = {"owner": "u", "path": "/a.txt", "size": 5, "block_hashes": ["h"]}
    r.save(doc)
    kwargs = col.replace_one.call_args.kwargs
    assert kwargs["filter"] == {"owner": "u", "path": "/a.txt"}
    assert kwargs["replacement"] == doc
    assert kwargs["upsert"] is True


def test_get_returns_document(repo):
    r, col = repo
    doc = {"owner": "u", "path": "/a.txt"}
    col.find_one.return_value = doc
    assert r.get("u", "/a.txt") == doc


def test_get_returns_none_when_missing_without_raising(repo):
    # Policy decision (raise 404) belongs to the service, not the repo.
    r, col = repo
    col.find_one.return_value = None
    assert r.get("u", "/missing") is None


def test_list_for_owner_applies_projection(repo):
    r, col = repo
    col.find.return_value = iter([{"owner": "u", "path": "/a.txt", "size": 5}])
    result = r.list_for_owner("u")
    args = col.find.call_args.args
    assert args[0] == {"owner": "u"}
    assert args[1] == {"_id": 0, "block_hashes": 0}
    assert result == [{"owner": "u", "path": "/a.txt", "size": 5}]
