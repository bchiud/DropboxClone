"""Contract tests for the ChangeBus port."""
import pytest

from app.ports.change_bus import ChangeBus


def test_cannot_instantiate_abstract_port():
    with pytest.raises(TypeError):
        ChangeBus()


def test_incomplete_implementation_is_rejected():
    class Incomplete(ChangeBus):
        async def publish(self, username):
            pass
        # missing listen

    with pytest.raises(TypeError):
        Incomplete()


def test_complete_implementation_instantiates():
    class Complete(ChangeBus):
        async def publish(self, username):
            pass

        async def listen(self, handler):
            pass

    assert isinstance(Complete(), ChangeBus)
