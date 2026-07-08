"""Route tests for the FastAPI app.

The FileService dependency is overridden with a fake, so routes are tested
in isolation from B2 / Mongo. Verifies request wiring and error translation.
"""
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.application.file_service import MissingBlocks
from app.auth_dependencies import get_current_user
from app.dependencies import get_file_service
from app.models.file import FileRecord, FileSummary
from app.main import app


class FakeService:
    def save_file(self, owner, path, data):
        return FileRecord(
            owner=owner, path=path, size=len(data),
            block_hashes=["h1"], updated_at=datetime.now(UTC),
        )

    def load_file(self, owner, path):
        if path == "/exists.txt":
            return b"hello bytes"
        raise FileNotFoundError(path)

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


@pytest.fixture
def client():
    app.dependency_overrides[get_file_service] = lambda: FakeService()
    app.dependency_overrides[get_current_user] = lambda: "test-user"
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_upload_returns_metadata(client):
    resp = client.post("/files?path=/a.txt", files={"file": ("a.txt", b"hello")})
    assert resp.status_code == 200
    assert resp.json() == {"path": "/a.txt", "size": 5, "blocks": 1}


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


def test_download_returns_bytes(client):
    resp = client.get("/files/content?path=/exists.txt")
    assert resp.status_code == 200
    assert resp.content == b"hello bytes"
    assert resp.headers["content-type"] == "application/octet-stream"


def test_download_missing_returns_404(client):
    resp = client.get("/files/content?path=/nope.txt")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "file not found"


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
