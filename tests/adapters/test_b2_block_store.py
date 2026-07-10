"""Unit tests for the B2 block-store adapter.

The boto3 client is injected as a mock — the whole point of the DI refactor
is that no module-level globals or real network are involved.
"""
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from app.adapters.b2_block_store import B2BlockStore
from app.ports.block_store import BlockStore

TTL = 42  # a sentinel, not the production default — see tests/test_config.py


def client_error(code):
    return ClientError({"Error": {"Code": code}}, "Op")


@pytest.fixture
def store():
    client = MagicMock()
    return B2BlockStore(client, "test-bucket", TTL), client


def test_is_a_block_store(store):
    s, _ = store
    assert isinstance(s, BlockStore)


def test_presigned_put_url_signs_put_object(store):
    s, client = store
    client.generate_presigned_url.return_value = "https://b2/put?sig=abc"
    url = s.presigned_put_url("h1")
    assert url == "https://b2/put?sig=abc"
    args = client.generate_presigned_url.call_args
    assert args.args[0] == "put_object"
    assert args.kwargs["Params"] == {"Bucket": "test-bucket", "Key": "h1"}


def test_presigned_get_url_signs_get_object(store):
    s, client = store
    client.generate_presigned_url.return_value = "https://b2/get?sig=xyz"
    url = s.presigned_get_url("h1")
    assert url == "https://b2/get?sig=xyz"
    args = client.generate_presigned_url.call_args
    assert args.args[0] == "get_object"
    assert args.kwargs["Params"] == {"Bucket": "test-bucket", "Key": "h1"}


def test_both_presigned_urls_expire_per_injected_ttl(store):
    s, client = store
    s.presigned_put_url("h1")
    assert client.generate_presigned_url.call_args.kwargs["ExpiresIn"] == TTL
    s.presigned_get_url("h1")
    assert client.generate_presigned_url.call_args.kwargs["ExpiresIn"] == TTL


@pytest.mark.parametrize("ttl", [60, 900])
def test_presigned_url_ttl_is_not_hardcoded(ttl):
    """Regression: ExpiresIn was a literal 3600, so revoking a grant left it readable
    for an hour. Asserting one sentinel can't distinguish 'reads the TTL' from 'happens
    to equal it' — vary the injected value and prove the URL tracks it."""
    client = MagicMock()
    B2BlockStore(client, "b", ttl).presigned_get_url("h1")
    assert client.generate_presigned_url.call_args.kwargs["ExpiresIn"] == ttl


def test_url_ttl_has_no_default():
    """Wiring it is not optional: a forgotten arg must fail loudly, never fall back
    to some shipped default that silently widens the revocation window."""
    with pytest.raises(TypeError):
        B2BlockStore(MagicMock(), "b")


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
