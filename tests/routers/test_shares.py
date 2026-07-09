"""Route tests for the /shares user-to-user grant endpoints.

The ShareService dependency is overridden with a fake; the authenticated user
is pinned to "bob" to verify the grant owner always comes from the token.
"""
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.auth_dependencies import get_current_user
from app.dependencies import get_share_service
from app.domain.security import decode_share_token
from app.main import app
from app.models.share import Share


class FakeShareService:
    def __init__(self):
        self.shared = None
        self.revoked = None

    def share(self, owner, path, shared_with):
        self.shared = (owner, path, shared_with)
        return Share(owner=owner, path=path, shared_with=shared_with,
                     created_at=datetime.now(UTC))

    def revoke(self, owner, path, shared_with):
        self.revoked = (owner, path, shared_with)

    def list_incoming(self, username):
        return [Share(owner="carol", path="/in.txt", shared_with=username,
                      created_at=datetime.now(UTC))]

    def list_outgoing(self, owner):
        return [Share(owner=owner, path="/out.txt", shared_with="dave",
                      created_at=datetime.now(UTC))]


@pytest.fixture
def service():
    svc = FakeShareService()
    app.dependency_overrides[get_share_service] = lambda: svc
    app.dependency_overrides[get_current_user] = lambda: "bob"
    yield svc
    app.dependency_overrides.clear()


def test_create_share_uses_the_token_as_owner(service):
    resp = TestClient(app).post(
        "/shares", json={"path": "/x.txt", "shared_with": "alice"})
    assert resp.status_code == 200
    # owner comes from the token, never the request body
    assert service.shared == ("bob", "/x.txt", "alice")
    assert resp.json()["owner"] == "bob"


def test_delete_share_revokes_and_returns_204(service):
    resp = TestClient(app).request(
        "DELETE", "/shares", json={"path": "/x.txt", "shared_with": "alice"})
    assert resp.status_code == 204
    assert service.revoked == ("bob", "/x.txt", "alice")


def test_incoming_lists_grants_to_the_caller(service):
    resp = TestClient(app).get("/shares/incoming")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["owner"] == "carol"
    assert body[0]["shared_with"] == "bob"


def test_outgoing_lists_grants_from_the_caller(service):
    resp = TestClient(app).get("/shares/outgoing")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["owner"] == "bob"
    assert body[0]["shared_with"] == "dave"


def test_create_link_mints_a_token_owned_by_the_caller(service):
    resp = TestClient(app).post("/shares/link", json={"path": "/x.txt"})
    assert resp.status_code == 200
    # owner is pinned to the token, redeemable back to (caller, path)
    assert decode_share_token(resp.json()["token"]) == ("bob", "/x.txt")


def test_shares_require_auth():
    resp = TestClient(app).get("/shares/incoming")
    assert resp.status_code == 401
