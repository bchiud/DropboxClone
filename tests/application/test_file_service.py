"""Unit tests for FileService — the domain layer.

Both ports are replaced with in-memory fakes, so this exercises the real
chunk -> store -> recipe -> reassemble logic with zero B2 / Mongo.
"""
import pytest

from app.config import settings
from app.domain import chunker
from app.models.file import FileRecord, FileSummary
from app.application.file_service import FileService
from app.ports.block_store import BlockStore
from app.ports.file_repository import FileRepository


class FakeBlockStore(BlockStore):
    def __init__(self):
        self.blocks: dict[str, bytes] = {}

    def has_block(self, h):
        return h in self.blocks

    def put_block(self, h, d):
        self.blocks[h] = d

    def get_block(self, h):
        return self.blocks[h]


class FakeFileRepository(FileRepository):
    def __init__(self):
        self.records: dict[tuple, FileRecord] = {}

    def save(self, record: FileRecord) -> None:
        self.records[(record.owner, record.path)] = record

    def get(self, owner, path) -> FileRecord | None:
        return self.records.get((owner, path))

    def list_for_owner(self, owner) -> list[FileSummary]:
        return [
            FileSummary(**r.model_dump())
            for (o, _), r in self.records.items()
            if o == owner
        ]


@pytest.fixture
def service():
    store = FakeBlockStore()
    repo = FakeFileRepository()
    return FileService(store, repo), store, repo


def test_save_returns_file_record(service):
    svc, _, _ = service
    data = b"hello world"
    rec = svc.save_file("u", "/a.txt", data)
    assert isinstance(rec, FileRecord)
    assert rec.owner == "u"
    assert rec.path == "/a.txt"
    assert rec.size == len(data)
    assert rec.block_hashes == [h for h, _ in chunker.split(data)]


def test_save_uploads_every_block(service):
    svc, store, _ = service
    data = b"hello world"
    svc.save_file("u", "/a.txt", data)
    for h, _ in chunker.split(data):
        assert h in store.blocks


def test_save_then_load_round_trips(service):
    svc, _, _ = service
    data = b"round trip payload " * 50
    svc.save_file("u", "/a.txt", data)
    assert svc.load_file("u", "/a.txt") == data


def test_load_missing_file_raises(service):
    svc, _, _ = service
    with pytest.raises(FileNotFoundError):
        svc.load_file("u", "/nope.txt")


def test_resaving_same_path_upserts(service):
    svc, _, repo = service
    svc.save_file("u", "/a.txt", b"first")
    svc.save_file("u", "/a.txt", b"second version")
    assert len(repo.records) == 1
    assert svc.load_file("u", "/a.txt") == b"second version"


def test_size_is_byte_length_not_block_count(service, monkeypatch):
    svc, _, _ = service
    monkeypatch.setattr(settings, "block_size", 4)  # force multiple blocks
    data = b"abcdefghij"  # 10 bytes -> 3 blocks
    rec = svc.save_file("u", "/a.txt", data)
    assert rec.size == 10
    assert len(rec.block_hashes) == 3


def test_different_owners_are_isolated(service):
    svc, _, _ = service
    svc.save_file("alice", "/shared.txt", b"alice data")
    svc.save_file("bob", "/shared.txt", b"bob data")
    assert svc.load_file("alice", "/shared.txt") == b"alice data"
    assert svc.load_file("bob", "/shared.txt") == b"bob data"


def test_identical_content_dedups_blocks(service):
    svc, store, _ = service
    svc.save_file("u", "/a.txt", b"same bytes")
    count = len(store.blocks)
    svc.save_file("u", "/b.txt", b"same bytes")  # identical content
    assert len(store.blocks) == count


def test_list_files_returns_summaries(service):
    svc, _, _ = service
    svc.save_file("u", "/a.txt", b"one")
    svc.save_file("u", "/b.txt", b"two")
    listed = svc.list_files("u")
    assert all(isinstance(s, FileSummary) for s in listed)
    assert {s.path for s in listed} == {"/a.txt", "/b.txt"}
