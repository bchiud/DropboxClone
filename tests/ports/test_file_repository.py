"""Contract tests for the FileRepository port."""
import pytest

from app.ports.file_repository import FileRepository


def test_cannot_instantiate_abstract_port():
    with pytest.raises(TypeError):
        FileRepository()


def test_incomplete_implementation_is_rejected():
    class Incomplete(FileRepository):
        def save(self, doc):
            pass
        # missing get / list_for_owner

    with pytest.raises(TypeError):
        Incomplete()


def test_complete_implementation_instantiates():
    class Complete(FileRepository):
        def save(self, doc):
            pass

        def get(self, owner, path):
            return None

        def delete(self, owner, path):
            return False

        def list_for_owner(self, owner):
            return []

    assert isinstance(Complete(), FileRepository)
