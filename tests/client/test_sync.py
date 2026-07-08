"""Unit tests for the SyncEngine using a fake in-memory API."""
import pytest

from client.state import LocalIndex
from client.sync import SyncEngine


class FakeApi:
    """In-memory stand-in for ApiClient: server_path -> bytes."""

    def __init__(self):
        self.store: dict[str, bytes] = {}

    def upload(self, path, data):
        self.store[path] = data
        return {"path": path, "size": len(data), "blocks": 1}

    def list_files(self):
        return [{"path": p} for p in self.store]

    def download(self, path):
        return self.store[path]


@pytest.fixture
def setup(tmp_path):
    folder = tmp_path / "sync"
    folder.mkdir()
    api = FakeApi()
    index = LocalIndex(tmp_path / "index.json")  # index lives OUTSIDE the synced folder
    return SyncEngine(api, index, folder), api, folder


def test_push_uploads_new_file(setup):
    engine, api, folder = setup
    (folder / "a.txt").write_bytes(b"hello")
    pushed = engine.push()
    assert pushed == ["/a.txt"]
    assert api.store["/a.txt"] == b"hello"


def test_push_skips_unchanged_file(setup):
    engine, _, folder = setup
    (folder / "a.txt").write_bytes(b"hello")
    engine.push()
    assert engine.push() == []  # nothing changed the second time


def test_push_detects_edit(setup):
    engine, api, folder = setup
    (folder / "a.txt").write_bytes(b"hello")
    engine.push()
    (folder / "a.txt").write_bytes(b"hello world")
    assert engine.push() == ["/a.txt"]
    assert api.store["/a.txt"] == b"hello world"


def test_push_handles_nested_paths(setup):
    engine, api, folder = setup
    (folder / "docs").mkdir()
    (folder / "docs" / "b.txt").write_bytes(b"x")
    engine.push()
    assert "/docs/b.txt" in api.store


def test_pull_downloads_remote_file(setup):
    engine, api, folder = setup
    api.store["/remote.txt"] = b"remote data"
    pulled = engine.pull()
    assert pulled == ["/remote.txt"]
    assert (folder / "remote.txt").read_bytes() == b"remote data"


def test_pull_creates_nested_directories(setup):
    engine, api, folder = setup
    api.store["/a/b/c.txt"] = b"deep"
    engine.pull()
    assert (folder / "a" / "b" / "c.txt").read_bytes() == b"deep"


def test_pull_skips_already_synced_file(setup):
    engine, api, folder = setup
    api.store["/remote.txt"] = b"data"
    engine.pull()
    assert engine.pull() == []  # already local and unchanged


def test_sync_propagates_between_two_folders(tmp_path):
    api = FakeApi()
    f1, f2 = tmp_path / "dev1", tmp_path / "dev2"
    f1.mkdir()
    f2.mkdir()
    e1 = SyncEngine(api, LocalIndex(tmp_path / "i1.json"), f1)
    e2 = SyncEngine(api, LocalIndex(tmp_path / "i2.json"), f2)

    (f1 / "shared.txt").write_bytes(b"from device 1")
    e1.sync()          # push to server
    e2.sync()          # pull to device 2

    assert (f2 / "shared.txt").read_bytes() == b"from device 1"


def test_sync_returns_pushed_and_pulled(setup):
    engine, api, folder = setup
    (folder / "local.txt").write_bytes(b"local")
    api.store["/remote.txt"] = b"remote"
    result = engine.sync()
    assert "/local.txt" in result["pushed"]
    assert "/remote.txt" in result["pulled"]
