"""Unit tests for FileService — block-negotiation orchestration.

Both ports are replaced with in-memory fakes, so these run with zero B2 / Mongo.
"""
import pytest

from app.application.file_service import BlockNotInFile, FileService, MissingBlocks
from app.domain.recipe import recipe_etag
from app.models.file import FileRecord, FileSummary
from app.ports.block_index import BlockIndex
from app.ports.block_store import BlockStore
from app.ports.file_repository import FileRepository, VersionConflict


class FakeBlockStore(BlockStore):
    def __init__(self):
        self.blocks: dict[str, bytes] = {}
        self.head_calls: list[str] = []  # every has_block(key) — to pin "HEADs only new"

    def has_block(self, h):
        self.head_calls.append(h)
        return h in self.blocks

    def presigned_put_url(self, h):
        return f"https://b2.test/put/{h}"

    def presigned_get_url(self, h):
        return f"https://b2.test/get/{h}"


class FakeFileRepository(FileRepository):
    def __init__(self):
        self.records: dict[tuple, FileRecord] = {}

    def save(self, record: FileRecord, expected_etag: str | None) -> None:
        # faithfully models the adapter's etag compare-and-swap so the concurrency
        # tests exercise real precondition logic, not a rubber stamp.
        key = (record.owner, record.path)
        existing = self.records.get(key)
        if expected_etag is None:  # create
            if existing is not None and existing.etag != record.etag:
                raise VersionConflict  # a *different* file already exists at this path
        elif existing is None or existing.etag not in (expected_etag, record.etag):
            raise VersionConflict  # base moved on (and it's not an idempotent retry)
        self.records[key] = record

    def get(self, owner, path) -> FileRecord | None:
        return self.records.get((owner, path))

    def delete(self, owner, path) -> bool:
        return self.records.pop((owner, path), None) is not None

    def list_for_owner(self, owner) -> list[FileSummary]:
        return [
            FileSummary(**r.model_dump())
            for (o, _), r in self.records.items()
            if o == owner
        ]


class FakeBlockIndex(BlockIndex):
    """In-memory owner -> {hashes known present in B2}. The invariant the real
    adapter upholds (index ⊆ B2) is the test's responsibility to respect."""

    def __init__(self):
        self._present: dict[str, set[str]] = {}

    def present_subset(self, owner, hashes):
        known = self._present.get(owner, set())
        return {h for h in hashes if h in known}

    def add_many(self, owner, hashes):
        self._present.setdefault(owner, set()).update(hashes)


@pytest.fixture
def service():
    store = FakeBlockStore()
    repo = FakeFileRepository()
    index = FakeBlockIndex()
    return FileService(store, repo, index), store, repo  # index reachable via svc._block_index


def test_missing_blocks_reads_the_index_not_b2(service):
    # a block in B2 but not yet indexed is still reported missing — proving the
    # negotiation path queries the index, not B2 (and it's the safe over-report).
    svc, store, _ = service
    store.blocks[FileService._block_key("u", "inb2")] = b"x"   # in B2, not committed/indexed
    svc._block_index.add_many("u", ["indexed"])
    assert svc.missing_blocks("u", ["indexed", "inb2"]) == ["inb2"]
    assert store.head_calls == []   # negotiation issues zero B2 HEADs


def test_upload_urls_are_put_urls_namespaced(service):
    svc, _, _ = service
    assert svc.upload_urls("u", ["h1"]) == {"h1": "https://b2.test/put/u/h1"}


def test_download_urls_are_get_urls_namespaced(service):
    svc, store, _ = service
    store.blocks[FileService._block_key("u", "h1")] = b"x"
    svc.commit_file("u", "/a.txt", 5, ["h1"], expected_etag=None)
    assert svc.download_urls("u", "/a.txt", ["h1"]) == {"h1": "https://b2.test/get/u/h1"}


def test_download_urls_rejects_hashes_not_in_the_recipe(service):
    # a hash the caller isn't authorized for (not part of this file) is refused,
    # even in the owner's own namespace — the recipe is the capability boundary.
    svc, store, _ = service
    store.blocks[FileService._block_key("u", "h1")] = b"x"
    svc.commit_file("u", "/a.txt", 5, ["h1"], expected_etag=None)
    with pytest.raises(BlockNotInFile) as exc:
        svc.download_urls("u", "/a.txt", ["h1", "other"])
    assert exc.value.hashes == ["other"]


def test_download_urls_raises_when_file_missing(service):
    # dangling grant / deleted-but-linked path: authz passed upstream, no recipe here
    svc, _, _ = service
    with pytest.raises(FileNotFoundError):
        svc.download_urls("u", "/nope.txt", ["h1"])


def test_block_keys_are_namespaced_per_owner(service):
    # cross-user isolation: same hash, different owners -> different storage keys
    svc, _, _ = service
    assert svc.upload_urls("alice", ["h"])["h"] != svc.upload_urls("bob", ["h"])["h"]


def test_commit_file_saves_when_all_blocks_present(service):
    svc, store, repo = service
    store.blocks[FileService._block_key("u", "h1")] = b"x"
    rec = svc.commit_file("u", "/a.txt", 5, ["h1"], expected_etag=None)
    assert rec.block_hashes == ["h1"]
    assert rec.updated_at is not None
    assert repo.get("u", "/a.txt") is not None


def test_commit_file_raises_when_blocks_missing(service):
    svc, _, _ = service
    with pytest.raises(MissingBlocks) as exc:
        svc.commit_file("u", "/a.txt", 5, ["nope"], expected_etag=None)
    assert exc.value.hashes == ["nope"]


def test_commit_indexes_new_blocks_after_verifying_them_in_b2(service):
    svc, store, _ = service
    store.blocks[FileService._block_key("u", "h1")] = b"x"   # uploaded to B2, not yet indexed
    svc.commit_file("u", "/a.txt", 5, ["h1"], expected_etag=None)
    assert svc._block_index.present_subset("u", ["h1"]) == {"h1"}   # now recorded


def test_commit_heads_only_unindexed_blocks(service):
    # already-indexed blocks were verified at their own commit -> trusted, not re-HEADed
    svc, store, _ = service
    svc._block_index.add_many("u", ["old"])                  # from a prior commit
    store.blocks[FileService._block_key("u", "new")] = b"x"
    svc.commit_file("u", "/a.txt", 5, ["old", "new"], expected_etag=None)
    assert store.head_calls == [FileService._block_key("u", "new")]  # "old" never touched B2


def test_commit_rejects_and_does_not_index_a_new_block_absent_from_b2(service):
    # the over-report guard: a hash neither indexed nor in B2 must 409, not slip into the index
    svc, _, _ = service
    with pytest.raises(MissingBlocks) as exc:
        svc.commit_file("u", "/a.txt", 5, ["ghost"], expected_etag=None)
    assert exc.value.hashes == ["ghost"]
    assert svc._block_index.present_subset("u", ["ghost"]) == set()  # not indexed on failure


def test_get_recipe_returns_full_record(service):
    svc, store, _ = service
    store.blocks[FileService._block_key("u", "h1")] = b"x"
    svc.commit_file("u", "/a.txt", 5, ["h1"], expected_etag=None)
    assert svc.get_recipe("u", "/a.txt").block_hashes == ["h1"]


def test_get_recipe_missing_raises(service):
    svc, _, _ = service
    with pytest.raises(FileNotFoundError):
        svc.get_recipe("u", "/nope.txt")


def test_delete_file_removes_the_record(service):
    svc, store, repo = service
    store.blocks[FileService._block_key("u", "h1")] = b"x"
    svc.commit_file("u", "/a.txt", 5, ["h1"], expected_etag=None)
    svc.delete_file("u", "/a.txt")
    assert repo.get("u", "/a.txt") is None


def test_delete_file_leaves_blocks_for_gc(service):
    # deletion removes the recipe only; the block survives for GC to reclaim.
    svc, store, repo = service
    key = FileService._block_key("u", "h1")
    store.blocks[key] = b"x"
    svc.commit_file("u", "/a.txt", 5, ["h1"], expected_etag=None)
    svc.delete_file("u", "/a.txt")
    assert key in store.blocks


def test_delete_file_missing_raises(service):
    svc, _, _ = service
    with pytest.raises(FileNotFoundError):
        svc.delete_file("u", "/nope.txt")


def test_list_files_returns_summaries(service):
    svc, store, _ = service
    store.blocks[FileService._block_key("u", "h1")] = b"x"
    svc.commit_file("u", "/a.txt", 5, ["h1"], expected_etag=None)
    svc.commit_file("u", "/b.txt", 5, ["h1"], expected_etag=None)
    listed = svc.list_files("u")
    assert all(isinstance(s, FileSummary) for s in listed)
    assert {s.path for s in listed} == {"/a.txt", "/b.txt"}


# --- optimistic concurrency (etag compare-and-swap) ---

def _stock(store, *hashes):
    for h in hashes:
        store.blocks[FileService._block_key("u", h)] = b"x"


def test_concurrent_update_off_same_base_etag_lets_exactly_one_win(service):
    svc, store, _ = service
    _stock(store, "h1", "h2", "h3")
    svc.commit_file("u", "/a.txt", 5, ["h1"], expected_etag=None)
    base = recipe_etag(["h1"])                                   # both clients read this
    svc.commit_file("u", "/a.txt", 5, ["h1", "h2"], expected_etag=base)   # first writer wins
    with pytest.raises(VersionConflict):                        # second raced off the same base
        svc.commit_file("u", "/a.txt", 5, ["h1", "h3"], expected_etag=base)


def test_duplicate_commit_is_a_no_op_not_a_conflict(service):
    # the $in fold: re-sending the same edit off a now-stale base still succeeds
    svc, store, repo = service
    _stock(store, "h1", "h2")
    svc.commit_file("u", "/a.txt", 5, ["h1"], expected_etag=None)
    base = recipe_etag(["h1"])
    svc.commit_file("u", "/a.txt", 5, ["h1", "h2"], expected_etag=base)   # applies
    svc.commit_file("u", "/a.txt", 5, ["h1", "h2"], expected_etag=base)   # retry -> no raise
    assert repo.get("u", "/a.txt").block_hashes == ["h1", "h2"]


def test_create_on_taken_path_with_different_content_conflicts(service):
    svc, store, _ = service
    _stock(store, "h1", "h2")
    svc.commit_file("u", "/a.txt", 5, ["h1"], expected_etag=None)
    with pytest.raises(VersionConflict):
        svc.commit_file("u", "/a.txt", 5, ["h2"], expected_etag=None)


def test_create_retry_with_same_content_is_idempotent(service):
    svc, store, _ = service
    _stock(store, "h1")
    svc.commit_file("u", "/a.txt", 5, ["h1"], expected_etag=None)
    svc.commit_file("u", "/a.txt", 5, ["h1"], expected_etag=None)  # retried create -> no raise
