"""Unit tests for the DI composition root."""
from unittest.mock import patch

import certifi

from app import dependencies
from app.domain.services import FileService
from app.ports.block_store import BlockStore
from app.ports.file_repository import FileRepository


def test_block_store_is_cached_singleton():
    dependencies.get_block_store.cache_clear()
    a = dependencies.get_block_store()
    b = dependencies.get_block_store()
    assert a is b  # @lru_cache returns the same instance
    assert isinstance(a, BlockStore)


def test_file_repository_uses_certifi_tls():
    """Regression: MongoClient must be constructed with tlsCAFile=certifi.where(),
    otherwise Atlas TLS fails on framework-Python macOS builds."""
    dependencies.get_file_repository.cache_clear()
    try:
        with patch("app.dependencies.MongoClient") as mock_client:
            dependencies.get_file_repository()
        assert mock_client.call_args.kwargs.get("tlsCAFile") == certifi.where()
    finally:
        dependencies.get_file_repository.cache_clear()


def test_file_repository_is_a_repository():
    dependencies.get_file_repository.cache_clear()
    repo = dependencies.get_file_repository()
    assert isinstance(repo, FileRepository)


def test_get_file_service_composes_a_service():
    svc = dependencies.get_file_service()
    assert isinstance(svc, FileService)
