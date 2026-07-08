"""Route tests for the FastAPI app.

The FileService dependency is overridden with a fake, so routes are tested
in isolation from B2 / Mongo. Verifies request wiring and error translation.
"""
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

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
