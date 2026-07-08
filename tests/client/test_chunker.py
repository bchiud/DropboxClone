"""Unit tests for the client-side chunker."""
import hashlib

from app.domain import chunker as server_chunker
from client import chunker


def test_hash_block_is_sha256():
    assert chunker.hash_block(b"abc") == hashlib.sha256(b"abc").hexdigest()


def test_split_cuts_at_block_size():
    pairs = list(chunker.split(b"abcdefghij", block_size=4))  # 4 + 4 + 2
    assert [len(b) for _, b in pairs] == [4, 4, 2]


def test_split_reassembles_losslessly():
    data = b"abcdefghij"
    pairs = list(chunker.split(data, block_size=4))
    assert b"".join(b for _, b in pairs) == data


def test_identical_blocks_hash_identically():
    pairs = list(chunker.split(b"aaaaaaaa", block_size=4))
    assert pairs[0][0] == pairs[1][0]


def test_empty_input_yields_nothing():
    assert list(chunker.split(b"")) == []


def test_small_file_is_single_block():
    pairs = list(chunker.split(b"hello"))  # default 4 MiB
    assert len(pairs) == 1
    assert pairs[0][1] == b"hello"


def test_agrees_with_server_chunker_on_hashes():
    # Block identity MUST match between client and server for the same bytes.
    data = b"the block hash is the shared contract " * 3
    client_hashes = [h for h, _ in chunker.split(data)]
    server_hashes = [h for h, _ in server_chunker.split(data)]
    assert client_hashes == server_hashes
