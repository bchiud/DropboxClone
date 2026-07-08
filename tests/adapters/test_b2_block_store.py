"""Unit tests for the B2 block-store adapter.

The boto3 client is injected as a mock — the whole point of the DI refactor
is that no module-level globals or real network are involved.
"""
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from app.adapters.b2_block_store import B2BlockStore
from app.ports.block_store import BlockStore


def client_error(code):
    return ClientError({"Error": {"Code": code}}, "Op")


@pytest.fixture
def store():
    client = MagicMock()
    return B2BlockStore(client, "test-bucket"), client


def test_is_a_block_store(store):
    s, _ = store
    assert isinstance(s, BlockStore)


def test_bucket_and_client_injected(store):
    s, client = store
    assert s._bucket == "test-bucket"
    assert s._s3 is client


def test_has_block_true_when_head_succeeds(store):
    s, client = store
    client.head_object.return_value = {"ContentLength": 4}
    assert s.has_block("h") is True


def test_has_block_false_on_404(store):
    s, client = store
    client.head_object.side_effect = client_error("404")
    assert s.has_block("h") is False


def test_has_block_reraises_non_404(store):
    s, client = store
    client.head_object.side_effect = client_error("403")
    with pytest.raises(ClientError):
        s.has_block("h")


def test_put_block_skips_when_present(store):
    s, client = store
    client.head_object.return_value = {}
    s.put_block("h", b"data")
    client.put_object.assert_not_called()


def test_put_block_writes_when_absent(store):
    s, client = store
    client.head_object.side_effect = client_error("404")
    s.put_block("h", b"data")
    client.put_object.assert_called_once()
    kwargs = client.put_object.call_args.kwargs
    assert kwargs["Bucket"] == "test-bucket"
    assert kwargs["Key"] == "h"
    assert kwargs["Body"] == b"data"


def test_get_block_reads_body(store):
    s, client = store
    body = MagicMock()
    body.read.return_value = b"payload"
    client.get_object.return_value = {"Body": body}
    assert s.get_block("h") == b"payload"
