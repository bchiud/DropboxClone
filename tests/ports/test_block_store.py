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
        # missing put_block / get_block

    with pytest.raises(TypeError):
        Incomplete()


def test_complete_implementation_instantiates():
    class Complete(BlockStore):
        def has_block(self, h):
            return False

        def put_block(self, h, d):
            pass

        def get_block(self, h):
            return b""

    assert isinstance(Complete(), BlockStore)
