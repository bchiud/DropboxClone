"""Unit tests for the Mongo block-index adapter.

The pymongo collection is injected as a mock; these verify the query vocabulary
(the `$in` presence lookup, the idempotent upsert) and the identity index.
"""
from unittest.mock import MagicMock

import pytest
from pymongo import UpdateOne

from app.adapters.mongo_block_index import MongoBlockIndex
from app.ports.block_index import BlockIndex


@pytest.fixture
def index():
    col = MagicMock()
    return MongoBlockIndex(col), col


def test_is_a_block_index(index):
    idx, _ = index
    assert isinstance(idx, BlockIndex)


def test_init_creates_the_unique_owner_hash_index(index):
    _, col = index
    col.create_index.assert_called_once_with([("owner", 1), ("hash", 1)], unique=True)


def test_present_subset_queries_in_and_returns_a_hash_set(index):
    idx, col = index
    col.find.return_value = iter([{"hash": "h1"}, {"hash": "h3"}])
    result = idx.present_subset("u", ["h1", "h2", "h3"])
    assert result == {"h1", "h3"}                       # only the present ones, as a set
    args = col.find.call_args.args
    assert args[0] == {"owner": "u", "hash": {"$in": ["h1", "h2", "h3"]}}
    assert args[1] == {"_id": 0, "hash": 1}             # project to just the hash


def test_add_many_upserts_each_hash_with_set_on_insert(index):
    idx, col = index
    idx.add_many("u", ["h1", "h2"])
    ops = col.bulk_write.call_args.args[0]
    assert ops == [
        UpdateOne({"owner": "u", "hash": "h1"},
                  {"$setOnInsert": {"owner": "u", "hash": "h1"}}, upsert=True),
        UpdateOne({"owner": "u", "hash": "h2"},
                  {"$setOnInsert": {"owner": "u", "hash": "h2"}}, upsert=True),
    ]
    assert col.bulk_write.call_args.kwargs["ordered"] is False


def test_add_many_with_no_hashes_is_a_noop(index):
    # bulk_write([]) raises InvalidOperation, so an empty batch must short-circuit
    idx, col = index
    idx.add_many("u", [])
    col.bulk_write.assert_not_called()
