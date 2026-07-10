"""Route tests for the FastAPI app.

The FileService dependency is overridden with a fake, so routes are tested
in isolation from B2 / Mongo. Verifies request wiring and error translation.
"""
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from unittest.mock import AsyncMock

from app.application.file_service import MissingBlocks
from app.auth_dependencies import get_current_user
from app.dependencies import get_notifier, get_file_service, get_share_service
from app.models.file import FileRecord, FileSummary
from app.main import app


class FakeService:
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

    def delete_file(self, owner, path):
        if path != "/known.txt":
            raise FileNotFoundError(path)


class FakeShareService:
    def __init__(self, allow=True, log=None, recipients=()):
        self.allow = allow
        self.log = log if log is not None else []
        self.recipients = list(recipients)  # who purge_for_file reports it dropped

    def can_read(self, requester, owner, path):
        return self.allow

    def purge_for_file(self, owner, path):
        self.log.append(("purge", owner, path))
        return self.recipients


@pytest.fixture
def client():
    app.dependency_overrides[get_file_service] = lambda: FakeService()
    app.dependency_overrides[get_share_service] = lambda: FakeShareService()
    app.dependency_overrides[get_current_user] = lambda: "test-user"
    yield TestClient(app)
    app.dependency_overrides.clear()


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


# --- delete ---

def test_delete_returns_204(client):
    resp = client.delete("/files", params={"path": "/known.txt"})
    assert resp.status_code == 204
    assert resp.content == b""  # 204 carries no body


def test_delete_missing_returns_404(client):
    resp = client.delete("/files", params={"path": "/nope.txt"})
    assert resp.status_code == 404


def test_delete_notifies_owner_on_success():
    notifier = AsyncMock()
    app.dependency_overrides[get_file_service] = lambda: FakeService()
    app.dependency_overrides[get_share_service] = lambda: FakeShareService()
    app.dependency_overrides[get_current_user] = lambda: "test-user"
    app.dependency_overrides[get_notifier] = lambda: notifier
    try:
        resp = TestClient(app).delete("/files", params={"path": "/known.txt"})
        assert resp.status_code == 204
        notifier.notify.assert_awaited_once_with("test-user")
    finally:
        app.dependency_overrides.clear()


def test_delete_does_not_notify_on_404():
    notifier = AsyncMock()
    app.dependency_overrides[get_file_service] = lambda: FakeService()
    app.dependency_overrides[get_share_service] = lambda: FakeShareService()
    app.dependency_overrides[get_current_user] = lambda: "test-user"
    app.dependency_overrides[get_notifier] = lambda: notifier
    try:
        resp = TestClient(app).delete("/files", params={"path": "/nope.txt"})
        assert resp.status_code == 404
        notifier.notify.assert_not_awaited()
    finally:
        app.dependency_overrides.clear()


# --- share-aware reads ---

def test_recipe_reads_a_shared_file_by_owner():
    app.dependency_overrides[get_file_service] = lambda: FakeService()
    app.dependency_overrides[get_current_user] = lambda: "alice"
    app.dependency_overrides[get_share_service] = lambda: FakeShareService(allow=True)
    try:
        resp = TestClient(app).get(
            "/files/recipe", params={"path": "/known.txt", "owner": "bob"})
        assert resp.status_code == 200
        assert resp.json()["block_hashes"] == ["h1", "h2"]
    finally:
        app.dependency_overrides.clear()


def test_recipe_without_grant_returns_404():
    app.dependency_overrides[get_file_service] = lambda: FakeService()
    app.dependency_overrides[get_current_user] = lambda: "alice"
    app.dependency_overrides[get_share_service] = lambda: FakeShareService(allow=False)
    try:
        resp = TestClient(app).get(
            "/files/recipe", params={"path": "/known.txt", "owner": "bob"})
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


# --- commit notifies over WebSocket ---

def test_commit_notifies_owner_on_success():
    notifier = AsyncMock()
    app.dependency_overrides[get_file_service] = lambda: FakeService()
    app.dependency_overrides[get_current_user] = lambda: "test-user"
    app.dependency_overrides[get_notifier] = lambda: notifier
    try:
        resp = TestClient(app).post(
            "/files/commit", json={"path": "/a.txt", "size": 5, "block_hashes": ["h1"]})
        assert resp.status_code == 201
        notifier.notify.assert_awaited_once_with("test-user")
    finally:
        app.dependency_overrides.clear()


def test_commit_does_not_notify_on_409():
    notifier = AsyncMock()
    app.dependency_overrides[get_file_service] = lambda: FakeService()
    app.dependency_overrides[get_current_user] = lambda: "test-user"
    app.dependency_overrides[get_notifier] = lambda: notifier
    try:
        resp = TestClient(app).post(
            "/files/commit", json={"path": "/a.txt", "size": 5, "block_hashes": ["missing"]})
        assert resp.status_code == 409
        notifier.notify.assert_not_awaited()
    finally:
        app.dependency_overrides.clear()


# --- delete cascades to grants ---

def _ordering_client():
    """A client whose file + share services append to one shared event log."""
    events = []

    class LoggingFileService(FakeService):
        def delete_file(self, owner, path):
            super().delete_file(owner, path)  # raises for an unknown path
            events.append(("delete", owner, path))  # only a real delete is logged

    app.dependency_overrides[get_file_service] = lambda: LoggingFileService()
    app.dependency_overrides[get_share_service] = lambda: FakeShareService(log=events)
    app.dependency_overrides[get_current_user] = lambda: "test-user"
    return TestClient(app), events


def test_delete_purges_grants_before_removing_the_recipe():
    """Purge-first fails safe: a crash mid-way leaves a live file with no grants,
    never a dead path with live grants (which would resurrect on re-upload)."""
    client, events = _ordering_client()
    try:
        assert client.delete("/files", params={"path": "/known.txt"}).status_code == 204
        assert events == [
            ("purge", "test-user", "/known.txt"),
            ("delete", "test-user", "/known.txt"),
        ]
    finally:
        app.dependency_overrides.clear()


def test_delete_of_a_missing_file_still_purges_its_dangling_grants():
    """404 path: grants on a file that doesn't exist are exactly the garbage
    purge-first is meant to collect, and owner comes from the token."""
    client, events = _ordering_client()
    try:
        assert client.delete("/files", params={"path": "/nope.txt"}).status_code == 404
        assert events == [("purge", "test-user", "/nope.txt")]  # no delete recorded
    finally:
        app.dependency_overrides.clear()


# --- delete notifies whoever's view changed ---

def _delete_client(recipients):
    notifier = AsyncMock()
    app.dependency_overrides[get_file_service] = lambda: FakeService()
    app.dependency_overrides[get_share_service] = lambda: FakeShareService(recipients=recipients)
    app.dependency_overrides[get_notifier] = lambda: notifier
    app.dependency_overrides[get_current_user] = lambda: "test-user"
    return TestClient(app), notifier


def test_delete_notifies_the_owner_and_every_purged_recipient():
    client, notifier = _delete_client(["alice", "carol"])
    try:
        assert client.delete("/files", params={"path": "/known.txt"}).status_code == 204
        awaited = [c.args[0] for c in notifier.notify.await_args_list]
        assert sorted(awaited) == ["alice", "carol", "test-user"]
    finally:
        app.dependency_overrides.clear()


def test_delete_of_a_missing_file_notifies_purged_recipients_but_not_the_owner():
    """Purge runs before the 404, so those grants really were dropped and the
    recipients' lists really did change. The owner's file list did not."""
    client, notifier = _delete_client(["alice"])
    try:
        assert client.delete("/files", params={"path": "/nope.txt"}).status_code == 404
        awaited = [c.args[0] for c in notifier.notify.await_args_list]
        assert awaited == ["alice"]
    finally:
        app.dependency_overrides.clear()
