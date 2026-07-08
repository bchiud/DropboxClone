"""Unit tests for FileService — block-negotiation orchestration.

Both ports are replaced with in-memory fakes, so these run with zero B2 / Mongo.
"""
import pytest

from app.application.file_service import FileService, MissingBlocks
from app.models.file import FileRecord, FileSummary
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

    def presigned_put_url(self, h):
        return f"https://b2.test/put/{h}"

    def presigned_get_url(self, h):
        return f"https://b2.test/get/{h}"


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


def test_missing_blocks_returns_only_absent(service):
    svc, store, _ = service
    store.blocks[FileService._block_key("u", "have")] = b"x"
    assert svc.missing_blocks("u", ["have", "gone"]) == ["gone"]


def test_upload_urls_are_put_urls_namespaced(service):
    svc, _, _ = service
    assert svc.upload_urls("u", ["h1"]) == {"h1": "https://b2.test/put/u/h1"}


def test_download_urls_are_get_urls_namespaced(service):
    svc, _, _ = service
    assert svc.download_urls("u", ["h1"]) == {"h1": "https://b2.test/get/u/h1"}


def test_block_keys_are_namespaced_per_owner(service):
    # cross-user isolation: same hash, different owners -> different storage keys
    svc, _, _ = service
    assert svc.upload_urls("alice", ["h"])["h"] != svc.upload_urls("bob", ["h"])["h"]


def test_commit_file_saves_when_all_blocks_present(service):
    svc, store, repo = service
    store.blocks[FileService._block_key("u", "h1")] = b"x"
    rec = svc.commit_file("u", "/a.txt", 5, ["h1"])
    assert rec.block_hashes == ["h1"]
    assert rec.updated_at is not None
    assert repo.get("u", "/a.txt") is not None


def test_commit_file_raises_when_blocks_missing(service):
    svc, _, _ = service
    with pytest.raises(MissingBlocks) as exc:
        svc.commit_file("u", "/a.txt", 5, ["nope"])
    assert exc.value.hashes == ["nope"]


def test_get_recipe_returns_full_record(service):
    svc, store, _ = service
    store.blocks[FileService._block_key("u", "h1")] = b"x"
    svc.commit_file("u", "/a.txt", 5, ["h1"])
    assert svc.get_recipe("u", "/a.txt").block_hashes == ["h1"]


def test_get_recipe_missing_raises(service):
    svc, _, _ = service
    with pytest.raises(FileNotFoundError):
        svc.get_recipe("u", "/nope.txt")


def test_list_files_returns_summaries(service):
    svc, store, _ = service
    store.blocks[FileService._block_key("u", "h1")] = b"x"
    svc.commit_file("u", "/a.txt", 5, ["h1"])
    svc.commit_file("u", "/b.txt", 5, ["h1"])
    listed = svc.list_files("u")
    assert all(isinstance(s, FileSummary) for s in listed)
    assert {s.path for s in listed} == {"/a.txt", "/b.txt"}
