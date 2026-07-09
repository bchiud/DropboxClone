"""Route tests for the public /link share-link endpoints.

These take no logged-in user — the signed share token IS the identity, so a
bad, forged, revoked, or expired token must 404 rather than reveal anything.
Revocation/expiry live in ShareService.resolve_link, so that is the seam we
fake here: a live token resolves to (owner, path); anything else resolves to
None (a forged/garbage/revoked/expired link is indistinguishable from the
router's point of view — all just "not found").
"""
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_file_service, get_share_service
from app.main import app
from app.models.file import FileRecord

GOOD_TOKEN = "live-token"
MISSING_FILE_TOKEN = "live-token-to-missing-file"


class FakeFileService:
    def get_recipe(self, owner, path):
        if path == "/known.txt":
            return FileRecord(owner=owner, path=path, size=3,
                              block_hashes=["h1", "h2"], updated_at=datetime.now(UTC))
        raise FileNotFoundError(path)

    def download_urls(self, owner, hashes):
        return {h: f"https://b2/get/{owner}/{h}" for h in hashes}


class FakeShareService:
    """Only the /link path is exercised here, so only resolve_link matters."""

    def resolve_link(self, token):
        if token == GOOD_TOKEN:
            return "bob", "/known.txt"
        if token == MISSING_FILE_TOKEN:
            return "bob", "/gone.txt"
        return None  # garbage, forged, revoked, or expired — all opaque


@pytest.fixture
def client():
    app.dependency_overrides[get_file_service] = lambda: FakeFileService()
    app.dependency_overrides[get_share_service] = lambda: FakeShareService()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_recipe_via_link_needs_no_login(client):
    resp = client.get("/link/recipe", params={"token": GOOD_TOKEN})
    assert resp.status_code == 200
    assert resp.json()["block_hashes"] == ["h1", "h2"]


def test_download_urls_via_link_namespaces_to_the_link_owner(client):
    resp = client.post("/link/download-urls",
                       params={"token": GOOD_TOKEN}, json={"hashes": ["h1"]})
    assert resp.json() == {"urls": {"h1": "https://b2/get/bob/h1"}}


def test_unresolvable_token_returns_404(client):
    # covers garbage / forged / revoked / expired — resolve_link returns None
    resp = client.get("/link/recipe", params={"token": "nope"})
    assert resp.status_code == 404


def test_download_urls_with_unresolvable_token_returns_404(client):
    resp = client.post("/link/download-urls",
                       params={"token": "nope"}, json={"hashes": ["h1"]})
    assert resp.status_code == 404


def test_link_to_missing_file_returns_404(client):
    # token resolves, but the file behind it is gone
    resp = client.get("/link/recipe", params={"token": MISSING_FILE_TOKEN})
    assert resp.status_code == 404
