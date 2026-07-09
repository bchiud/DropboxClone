"""Route tests for the FastAPI app.

The FileService dependency is overridden with a fake, so routes are tested
in isolation from B2 / Mongo. Verifies request wiring and error translation.
"""
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from unittest.mock import AsyncMock

from app.application.file_service import MissingBlocks
from app.auth_dependencies import get_current_user
from app.dependencies import get_connection_manager, get_file_service, get_share_service
from app.models.file import FileRecord, FileSummary
from app.main import app


class FakeService:
    def list_files(self, owner):
        return [FileSummary(owner=owner, path="/a.txt", size=5, updated_at=datetime.now(UTC))]

    def commit_file(self, owner, path, size, block_hashes):
        if "missing" in block_hashes:
            raise MissingBlocks(["missing"])
        return FileRecord(
            owner=owner, path=path, size=size,
            block_hashes=block_hashes, updated_at=datetime.now(UTC),
        )

    def get_recipe(self, owner, path):
        if path == "/known.txt":
            return FileRecord(
                owner=owner, path=path, size=3,
                block_hashes=["h1", "h2"], updated_at=datetime.now(UTC),
            )
        raise FileNotFoundError(path)

    def delete_file(self, owner, path):
        if path != "/known.txt":
            raise FileNotFoundError(path)


class FakeShareService:
    def __init__(self, allow):
        self.allow = allow

    def can_read(self, requester, owner, path):
        return self.allow


@pytest.fixture
def client():
    app.dependency_overrides[get_file_service] = lambda: FakeService()
    app.dependency_overrides[get_current_user] = lambda: "test-user"
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_list_returns_summaries_without_recipe(client):
    resp = client.get("/files")
    assert resp.status_code == 200
    files = resp.json()["files"]
    assert len(files) == 1
    assert files[0]["path"] == "/a.txt"
    assert files[0]["size"] == 5
    assert files[0]["owner"] == "test-user"
    assert "updated_at" in files[0]
    assert "block_hashes" not in files[0]  # summary must not leak the recipe


# --- delta-flow endpoints ---

def test_commit_returns_201(client):
    resp = client.post("/files/commit",
                       json={"path": "/a.txt", "size": 5, "block_hashes": ["h1"]})
    assert resp.status_code == 201
    assert resp.json() == {"path": "/a.txt", "size": 5, "blocks": 1}


def test_commit_missing_blocks_returns_409(client):
    resp = client.post("/files/commit",
                       json={"path": "/a.txt", "size": 5, "block_hashes": ["missing"]})
    assert resp.status_code == 409
    assert resp.json()["detail"]["missing"] == ["missing"]


def test_recipe_returns_block_hashes(client):
    resp = client.get("/files/recipe", params={"path": "/known.txt"})
    assert resp.status_code == 200
    assert resp.json()["block_hashes"] == ["h1", "h2"]


def test_recipe_missing_returns_404(client):
    resp = client.get("/files/recipe", params={"path": "/nope.txt"})
    assert resp.status_code == 404


# --- delete ---

def test_delete_returns_204(client):
    resp = client.delete("/files", params={"path": "/known.txt"})
    assert resp.status_code == 204
    assert resp.content == b""  # 204 carries no body


def test_delete_missing_returns_404(client):
    resp = client.delete("/files", params={"path": "/nope.txt"})
    assert resp.status_code == 404


def test_delete_notifies_owner_on_success():
    manager = AsyncMock()
    app.dependency_overrides[get_file_service] = lambda: FakeService()
    app.dependency_overrides[get_current_user] = lambda: "test-user"
    app.dependency_overrides[get_connection_manager] = lambda: manager
    try:
        resp = TestClient(app).delete("/files", params={"path": "/known.txt"})
        assert resp.status_code == 204
        manager.notify.assert_awaited_once_with("test-user")
    finally:
        app.dependency_overrides.clear()


def test_delete_does_not_notify_on_404():
    manager = AsyncMock()
    app.dependency_overrides[get_file_service] = lambda: FakeService()
    app.dependency_overrides[get_current_user] = lambda: "test-user"
    app.dependency_overrides[get_connection_manager] = lambda: manager
    try:
        resp = TestClient(app).delete("/files", params={"path": "/nope.txt"})
        assert resp.status_code == 404
        manager.notify.assert_not_awaited()
    finally:
        app.dependency_overrides.clear()


# --- share-aware reads ---

def test_recipe_reads_a_shared_file_by_owner():
    app.dependency_overrides[get_file_service] = lambda: FakeService()
    app.dependency_overrides[get_current_user] = lambda: "alice"
    app.dependency_overrides[get_share_service] = lambda: FakeShareService(allow=True)
    try:
        resp = TestClient(app).get(
            "/files/recipe", params={"path": "/known.txt", "owner": "bob"})
        assert resp.status_code == 200
        assert resp.json()["block_hashes"] == ["h1", "h2"]
    finally:
        app.dependency_overrides.clear()


def test_recipe_without_grant_returns_404():
    app.dependency_overrides[get_file_service] = lambda: FakeService()
    app.dependency_overrides[get_current_user] = lambda: "alice"
    app.dependency_overrides[get_share_service] = lambda: FakeShareService(allow=False)
    try:
        resp = TestClient(app).get(
            "/files/recipe", params={"path": "/known.txt", "owner": "bob"})
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


# --- commit notifies over WebSocket ---

def test_commit_notifies_owner_on_success():
    manager = AsyncMock()
    app.dependency_overrides[get_file_service] = lambda: FakeService()
    app.dependency_overrides[get_current_user] = lambda: "test-user"
    app.dependency_overrides[get_connection_manager] = lambda: manager
    try:
        resp = TestClient(app).post(
            "/files/commit", json={"path": "/a.txt", "size": 5, "block_hashes": ["h1"]})
        assert resp.status_code == 201
        manager.notify.assert_awaited_once_with("test-user")
    finally:
        app.dependency_overrides.clear()


def test_commit_does_not_notify_on_409():
    manager = AsyncMock()
    app.dependency_overrides[get_file_service] = lambda: FakeService()
    app.dependency_overrides[get_current_user] = lambda: "test-user"
    app.dependency_overrides[get_connection_manager] = lambda: manager
    try:
        resp = TestClient(app).post(
            "/files/commit", json={"path": "/a.txt", "size": 5, "block_hashes": ["missing"]})
        assert resp.status_code == 409
        manager.notify.assert_not_awaited()
    finally:
        app.dependency_overrides.clear()
