"""Contract tests for the BlockStore port."""
import pytest

from app.ports.block_store import BlockStore


def test_cannot_instantiate_abstract_port():
    with pytest.raises(TypeError):
        BlockStore()


def test_incomplete_implementation_is_rejected():
    class Incomplete(BlockStore):
        def has_block(self, h):
            return False
        # missing presigned_put_url / presigned_get_url

    with pytest.raises(TypeError):
        Incomplete()


def test_complete_implementation_instantiates():
    class Complete(BlockStore):
        def has_block(self, h):
            return False

        def presigned_put_url(self, h):
            return ""

        def presigned_get_url(self, h):
            return ""

    assert isinstance(Complete(), BlockStore)


def test_port_exposes_no_byte_moving_methods():
    """Bytes go client -> B2 directly. A put_block/get_block on the port would be
    an invitation to route them through the app server."""
    assert not hasattr(BlockStore, "put_block")
    assert not hasattr(BlockStore, "get_block")
