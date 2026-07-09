"""Route tests for the /blocks delta-negotiation endpoints.

The FileService dependency is overridden with a fake; the authenticated user
is pinned to "alice" to verify owner-namespacing flows through to the service.
"""
import pytest
from fastapi.testclient import TestClient

from app.auth_dependencies import get_current_user
from app.dependencies import get_file_service, get_share_service
from app.main import app


class FakeService:
    def missing_blocks(self, owner, hashes):
        return [h for h in hashes if h != "have"]

    def upload_urls(self, owner, hashes):
        return {h: f"https://b2/put/{owner}/{h}" for h in hashes}

    def download_urls(self, owner, hashes):
        return {h: f"https://b2/get/{owner}/{h}" for h in hashes}


class FakeShareService:
    def __init__(self, allow):
        self.allow = allow

    def can_read(self, requester, owner, path):
        return self.allow


@pytest.fixture
def client():
    app.dependency_overrides[get_file_service] = lambda: FakeService()
    app.dependency_overrides[get_current_user] = lambda: "alice"
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_missing_returns_absent_hashes(client):
    resp = client.post("/blocks/missing", json={"hashes": ["have", "gone"]})
    assert resp.status_code == 200
    assert resp.json() == {"missing": ["gone"]}


def test_upload_urls_wrapped_and_owner_namespaced(client):
    resp = client.post("/blocks/upload-urls", json={"hashes": ["h1"]})
    assert resp.json() == {"urls": {"h1": "https://b2/put/alice/h1"}}


def test_download_urls_wrapped_and_owner_namespaced(client):
    resp = client.post("/blocks/download-urls", json={"hashes": ["h1"]})
    assert resp.json() == {"urls": {"h1": "https://b2/get/alice/h1"}}


def test_download_urls_for_a_shared_owner_namespaces_to_that_owner(client):
    app.dependency_overrides[get_share_service] = lambda: FakeShareService(allow=True)
    resp = client.post(
        "/blocks/download-urls", params={"owner": "bob", "path": "/x.txt"},
        json={"hashes": ["h1"]})
    assert resp.json() == {"urls": {"h1": "https://b2/get/bob/h1"}}


def test_download_urls_without_grant_returns_404(client):
    app.dependency_overrides[get_share_service] = lambda: FakeShareService(allow=False)
    resp = client.post(
        "/blocks/download-urls", params={"owner": "bob", "path": "/x.txt"},
        json={"hashes": ["h1"]})
    assert resp.status_code == 404


def test_blocks_require_auth():
    # no get_current_user override -> real dependency rejects missing token
    resp = TestClient(app).post("/blocks/missing", json={"hashes": ["h1"]})
    assert resp.status_code == 401
