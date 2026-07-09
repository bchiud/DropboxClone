"""Route tests for the /shares user-to-user grant endpoints.

The ShareService dependency is overridden with a fake; the authenticated user
is pinned to "bob" to verify the grant owner always comes from the token.
"""
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.auth_dependencies import get_current_user
from app.dependencies import get_share_service
from app.main import app
from app.models.share import Share, ShareLink


class FakeShareService:
    def __init__(self):
        self.shared = None
        self.revoked = None
        self.linked = None
        self.revoked_link = None

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

    def create_link(self, owner, path):
        self.linked = (owner, path)
        return "minted-token"

    def revoke_link(self, owner, jti):
        self.revoked_link = (owner, jti)

    def list_links(self, owner):
        return [ShareLink(jti="j1", owner=owner, path="/l.txt",
                          created_at=datetime.now(UTC), expires_at=datetime.now(UTC))]


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


def test_create_link_pins_owner_to_the_caller(service):
    resp = TestClient(app).post("/shares/link", json={"path": "/x.txt"})
    assert resp.status_code == 200
    # owner comes from the token, never the request body
    assert service.linked == ("bob", "/x.txt")
    assert resp.json()["token"] == "minted-token"


def test_revoke_link_is_scoped_to_the_caller(service):
    resp = TestClient(app).delete("/shares/link/j1")
    assert resp.status_code == 204
    # revoke carries the caller as owner so one user can't revoke another's link
    assert service.revoked_link == ("bob", "j1")


def test_list_links_returns_the_callers_links(service):
    resp = TestClient(app).get("/shares/link")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["owner"] == "bob"
    assert body[0]["jti"] == "j1"


def test_shares_require_auth():
    resp = TestClient(app).get("/shares/incoming")
    assert resp.status_code == 401
