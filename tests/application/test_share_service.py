"""Unit tests for ShareService (the authorization layer)."""
from datetime import UTC, datetime

import pytest

from app.application.share_service import ShareService
from app.models.share import Share


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


@pytest.fixture
def service():
    repo = FakeShareRepository()
    return ShareService(repo), repo


def test_share_creates_a_timestamped_grant(service):
    svc, repo = service
    share = svc.share("bob", "/x.txt", "alice")
    assert isinstance(share, Share)
    assert (share.owner, share.path, share.shared_with) == ("bob", "/x.txt", "alice")
    assert share.created_at.tzinfo is UTC
    assert repo.shares[("bob", "/x.txt", "alice")] is share


def test_can_read_is_true_for_the_owner(service):
    svc, _ = service
    assert svc.can_read("bob", "bob", "/x.txt") is True


def test_can_read_is_true_for_a_granted_recipient(service):
    svc, _ = service
    svc.share("bob", "/x.txt", "alice")
    assert svc.can_read("alice", "bob", "/x.txt") is True


def test_can_read_is_false_for_a_stranger(service):
    svc, _ = service
    svc.share("bob", "/x.txt", "alice")
    assert svc.can_read("mallory", "bob", "/x.txt") is False


def test_revoke_removes_access(service):
    svc, _ = service
    svc.share("bob", "/x.txt", "alice")
    svc.revoke("bob", "/x.txt", "alice")
    assert svc.can_read("alice", "bob", "/x.txt") is False


def test_list_incoming_returns_grants_to_the_recipient(service):
    svc, _ = service
    svc.share("bob", "/x.txt", "alice")
    svc.share("carol", "/y.txt", "alice")
    svc.share("bob", "/z.txt", "dave")
    incoming = svc.list_incoming("alice")
    assert {s.owner for s in incoming} == {"bob", "carol"}


def test_list_outgoing_returns_grants_from_the_owner(service):
    svc, _ = service
    svc.share("bob", "/x.txt", "alice")
    svc.share("bob", "/y.txt", "dave")
    svc.share("carol", "/z.txt", "alice")
    outgoing = svc.list_outgoing("bob")
    assert {s.path for s in outgoing} == {"/x.txt", "/y.txt"}
