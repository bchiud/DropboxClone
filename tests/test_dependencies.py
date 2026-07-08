"""Unit tests for the DI composition root."""
from unittest.mock import patch

import certifi

from app import dependencies
from app.application.auth_service import AuthService
from app.application.file_service import FileService
from app.ports.block_store import BlockStore
from app.ports.file_repository import FileRepository
from app.ports.user_repository import UserRepository
from app.realtime import ConnectionManager


def test_block_store_is_cached_singleton():
    dependencies.get_block_store.cache_clear()
    a = dependencies.get_block_store()
    b = dependencies.get_block_store()
    assert a is b  # @lru_cache returns the same instance
    assert isinstance(a, BlockStore)


def test_database_uses_certifi_tls():
    """Regression: MongoClient must be constructed with tlsCAFile=certifi.where(),
    otherwise Atlas TLS fails on framework-Python macOS builds. The single
    MongoClient now lives in _get_database, shared by both repositories."""
    dependencies._get_database.cache_clear()
    try:
        with patch("app.dependencies.MongoClient") as mock_client:
            dependencies._get_database()
        assert mock_client.call_args.kwargs.get("tlsCAFile") == certifi.where()
    finally:
        dependencies._get_database.cache_clear()


def test_file_repository_is_a_repository():
    dependencies.get_file_repository.cache_clear()
    repo = dependencies.get_file_repository()
    assert isinstance(repo, FileRepository)


def test_user_repository_is_a_user_repository():
    dependencies.get_user_repository.cache_clear()
    repo = dependencies.get_user_repository()
    assert isinstance(repo, UserRepository)


def test_get_file_service_composes_a_service():
    svc = dependencies.get_file_service()
    assert isinstance(svc, FileService)


def test_get_auth_service_composes_a_service():
    svc = dependencies.get_auth_service()
    assert isinstance(svc, AuthService)


def test_connection_manager_is_cached_singleton():
    dependencies.get_connection_manager.cache_clear()
    a = dependencies.get_connection_manager()
    b = dependencies.get_connection_manager()
    assert a is b
    assert isinstance(a, ConnectionManager)
