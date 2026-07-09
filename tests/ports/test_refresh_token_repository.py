"""Contract tests for the RefreshTokenRepository port."""
import pytest

from app.ports.refresh_token_repository import RefreshTokenRepository


def test_cannot_instantiate_abstract_port():
    with pytest.raises(TypeError):
        RefreshTokenRepository()


def test_incomplete_implementation_is_rejected():
    class Incomplete(RefreshTokenRepository):
        def add(self, token):
            pass
        # missing exists / delete

    with pytest.raises(TypeError):
        Incomplete()


def test_complete_implementation_instantiates():
    class Complete(RefreshTokenRepository):
        def add(self, token):
            pass

        def exists(self, jti):
            return False

        def delete(self, jti):
            pass

    assert isinstance(Complete(), RefreshTokenRepository)
