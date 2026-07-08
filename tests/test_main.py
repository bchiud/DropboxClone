"""Route tests for the FastAPI app.

The FileService dependency is overridden with a fake, so routes are tested
in isolation from B2 / Mongo. Verifies request wiring and error translation.
"""
import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_file_service
from app.main import app


class FakeService:
    def save_file(self, owner, path, data):
        return {"path": path, "size": len(data), "block_hashes": ["h1"]}

    def load_file(self, owner, path):
        if path == "/exists.txt":
            return b"hello bytes"
        raise FileNotFoundError(path)

    def list_files(self, owner):
        return [{"owner": owner, "path": "/a.txt", "size": 5}]


@pytest.fixture
def client():
    app.dependency_overrides[get_file_service] = lambda: FakeService()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_upload_returns_metadata(client):
    resp = client.post("/files?path=/a.txt", files={"file": ("a.txt", b"hello")})
    assert resp.status_code == 200
    assert resp.json() == {"path": "/a.txt", "size": 5, "blocks": 1}


def test_list_returns_files(client):
    resp = client.get("/files")
    assert resp.status_code == 200
    assert resp.json() == {"files": [{"owner": "test-user", "path": "/a.txt", "size": 5}]}


def test_download_returns_bytes(client):
    resp = client.get("/files/content?path=/exists.txt")
    assert resp.status_code == 200
    assert resp.content == b"hello bytes"
    assert resp.headers["content-type"] == "application/octet-stream"


def test_download_missing_returns_404(client):
    resp = client.get("/files/content?path=/nope.txt")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "file not found"
