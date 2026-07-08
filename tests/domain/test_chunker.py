"""Unit tests for app/chunker.py — pure chunking logic, no I/O."""
import hashlib

import pytest

from app.config import settings
from app.domain import chunker


@pytest.fixture
def tiny_blocks(monkeypatch):
    """Shrink block size to 4 bytes so boundaries are easy to assert."""
    monkeypatch.setattr(settings, "block_size", 4)


def test_hash_block_is_sha256_hex():
    assert chunker.hash_block(b"abc") == hashlib.sha256(b"abc").hexdigest()


def test_split_cuts_at_block_size(tiny_blocks):
    pairs = list(chunker.split(b"abcdefghij"))  # 10 bytes -> 4 + 4 + 2
    assert [len(block) for _, block in pairs] == [4, 4, 2]


def test_split_reassembles_losslessly(tiny_blocks):
    data = b"abcdefghij"
    pairs = list(chunker.split(data))
    assert b"".join(block for _, block in pairs) == data


def test_each_hash_matches_its_block(tiny_blocks):
    for h, block in chunker.split(b"abcdefghij"):
        assert h == hashlib.sha256(block).hexdigest()


def test_identical_blocks_hash_identically(tiny_blocks):
    pairs = list(chunker.split(b"aaaaaaaa"))  # two identical 'aaaa' blocks
    assert pairs[0][0] == pairs[1][0]


def test_empty_input_yields_nothing():
    assert list(chunker.split(b"")) == []


def test_data_smaller_than_block_is_single_block():
    # default block_size (4 MiB) is far larger than this input
    pairs = list(chunker.split(b"hello"))
    assert len(pairs) == 1
    assert pairs[0][1] == b"hello"


def test_data_exactly_one_block(tiny_blocks):
    pairs = list(chunker.split(b"abcd"))  # exactly 4 bytes
    assert len(pairs) == 1
    assert pairs[0][1] == b"abcd"


def test_returns_an_iterator_not_a_list():
    # split should stream, not materialize everything up front
    result = chunker.split(b"hello")
    assert iter(result) is iter(result)
