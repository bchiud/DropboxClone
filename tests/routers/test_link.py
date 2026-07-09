"""Route tests for the public /link share-link endpoints.

These take no logged-in user — the signed share token IS the identity, so a
bad or forged token must 404 rather than reveal anything.
"""
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_file_service
from app.domain.security import create_share_token
from app.main import app
from app.models.file import FileRecord


class FakeService:
    def get_recipe(self, owner, path):
        if path == "/known.txt":
            return FileRecord(owner=owner, path=path, size=3,
                              block_hashes=["h1", "h2"], updated_at=datetime.now(UTC))
        raise FileNotFoundError(path)

    def download_urls(self, owner, hashes):
        return {h: f"https://b2/get/{owner}/{h}" for h in hashes}


@pytest.fixture
def client():
    app.dependency_overrides[get_file_service] = lambda: FakeService()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_recipe_via_link_needs_no_login(client):
    token = create_share_token("bob", "/known.txt")
    resp = client.get("/link/recipe", params={"token": token})
    assert resp.status_code == 200
    assert resp.json()["block_hashes"] == ["h1", "h2"]


def test_download_urls_via_link_namespaces_to_the_link_owner(client):
    token = create_share_token("bob", "/known.txt")
    resp = client.post("/link/download-urls",
                       params={"token": token}, json={"hashes": ["h1"]})
    assert resp.json() == {"urls": {"h1": "https://b2/get/bob/h1"}}


def test_bad_token_returns_404(client):
    resp = client.get("/link/recipe", params={"token": "garbage"})
    assert resp.status_code == 404


def test_link_to_missing_file_returns_404(client):
    token = create_share_token("bob", "/gone.txt")
    resp = client.get("/link/recipe", params={"token": token})
    assert resp.status_code == 404
