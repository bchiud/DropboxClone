"""Unit tests for ShareService (the authorization layer)."""
from datetime import UTC, datetime

import pytest

from app.application.share_service import ShareService
from app.config import settings
from app.models.share import Share, ShareLink


class FakeShareRepository:
    """In-memory ShareRepository keyed on the (owner, path, shared_with) triple."""

    def __init__(self) -> None:
        self.shares: dict[tuple[str, str, str], Share] = {}

    def add(self, share: Share) -> None:
        self.shares[(share.owner, share.path, share.shared_with)] = share

    def remove(self, owner: str, path: str, shared_with: str) -> None:
        self.shares.pop((owner, path, shared_with), None)

    def exists(self, owner: str, path: str, shared_with: str) -> bool:
        return (owner, path, shared_with) in self.shares

    def list_for_recipient(self, username: str) -> list[Share]:
        return [s for s in self.shares.values() if s.shared_with == username]

    def list_for_owner(self, owner: str) -> list[Share]:
        return [s for s in self.shares.values() if s.owner == owner]


class FakeShareLinkRepository:
    """In-memory ShareLinkRepository keyed on jti; delete is owner-scoped."""

    def __init__(self) -> None:
        self.links: dict[str, ShareLink] = {}

    def add(self, link: ShareLink) -> None:
        self.links[link.jti] = link

    def delete(self, owner: str, jti: str) -> None:
        if jti in self.links and self.links[jti].owner == owner:
            del self.links[jti]

    def exists(self, jti: str) -> bool:
        return jti in self.links

    def list_for_owner(self, owner: str) -> list[ShareLink]:
        return [ln for ln in self.links.values() if ln.owner == owner]


@pytest.fixture
def service():
    repo = FakeShareRepository()
    links = FakeShareLinkRepository()
    return ShareService(repo, links), repo, links


# --- user-to-user sharing ---

def test_share_creates_a_timestamped_grant(service):
    svc, repo, _ = service
    share = svc.share("bob", "/x.txt", "alice")
    assert isinstance(share, Share)
    assert (share.owner, share.path, share.shared_with) == ("bob", "/x.txt", "alice")
    assert share.created_at.tzinfo is UTC
    assert repo.shares[("bob", "/x.txt", "alice")] is share


def test_can_read_is_true_for_the_owner(service):
    svc, _, _ = service
    assert svc.can_read("bob", "bob", "/x.txt") is True


def test_can_read_is_true_for_a_granted_recipient(service):
    svc, _, _ = service
    svc.share("bob", "/x.txt", "alice")
    assert svc.can_read("alice", "bob", "/x.txt") is True


def test_can_read_is_false_for_a_stranger(service):
    svc, _, _ = service
    svc.share("bob", "/x.txt", "alice")
    assert svc.can_read("mallory", "bob", "/x.txt") is False


def test_revoke_removes_access(service):
    svc, _, _ = service
    svc.share("bob", "/x.txt", "alice")
    svc.revoke("bob", "/x.txt", "alice")
    assert svc.can_read("alice", "bob", "/x.txt") is False


def test_list_incoming_returns_grants_to_the_recipient(service):
    svc, _, _ = service
    svc.share("bob", "/x.txt", "alice")
    svc.share("carol", "/y.txt", "alice")
    svc.share("bob", "/z.txt", "dave")
    incoming = svc.list_incoming("alice")
    assert {s.owner for s in incoming} == {"bob", "carol"}


def test_list_outgoing_returns_grants_from_the_owner(service):
    svc, _, _ = service
    svc.share("bob", "/x.txt", "alice")
    svc.share("bob", "/y.txt", "dave")
    svc.share("carol", "/z.txt", "alice")
    outgoing = svc.list_outgoing("bob")
    assert {s.path for s in outgoing} == {"/x.txt", "/y.txt"}


# --- public link sharing ---

def test_create_link_stores_a_row_and_returns_a_resolvable_token(service):
    svc, _, links = service
    token = svc.create_link("bob", "/x.txt")
    assert len(links.links) == 1                       # one live row
    assert svc.resolve_link(token) == ("bob", "/x.txt")


def test_resolve_link_rejects_a_garbage_token(service):
    svc, _, _ = service
    assert svc.resolve_link("not.a.jwt") is None


def test_revoked_link_no_longer_resolves(service):
    svc, _, links = service
    token = svc.create_link("bob", "/x.txt")
    jti = next(iter(links.links))
    svc.revoke_link("bob", jti)
    assert svc.resolve_link(token) is None             # row gone -> revoked


def test_revoke_link_is_owner_scoped(service):
    svc, _, links = service
    token = svc.create_link("bob", "/x.txt")
    jti = next(iter(links.links))
    svc.revoke_link("mallory", jti)                     # not the owner -> no-op
    assert svc.resolve_link(token) == ("bob", "/x.txt")


def test_expired_link_does_not_resolve(service, monkeypatch):
    svc, _, _ = service
    monkeypatch.setattr(settings, "share_link_expire_minutes", -1)  # already expired
    token = svc.create_link("bob", "/x.txt")
    assert svc.resolve_link(token) is None             # exp enforced at decode


def test_list_links_returns_the_owners_links(service):
    svc, _, _ = service
    svc.create_link("bob", "/x.txt")
    svc.create_link("bob", "/y.txt")
    svc.create_link("carol", "/z.txt")
    paths = {ln.path for ln in svc.list_links("bob")}
    assert paths == {"/x.txt", "/y.txt"}
