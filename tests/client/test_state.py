"""Unit tests for the client-side LocalIndex."""
from client.state import LocalIndex


def test_new_file_is_changed(tmp_path):
    idx = LocalIndex(tmp_path / "index.json")
    assert idx.is_changed("a.txt", b"hello") is True  # never seen


def test_unchanged_file_is_not_changed(tmp_path):
    idx = LocalIndex(tmp_path / "index.json")
    idx.update("a.txt", b"hello", "etag-1")
    assert idx.is_changed("a.txt", b"hello") is False


def test_edited_file_is_changed(tmp_path):
    idx = LocalIndex(tmp_path / "index.json")
    idx.update("a.txt", b"hello", "etag-1")
    assert idx.is_changed("a.txt", b"hello world") is True


def test_persists_across_reload(tmp_path):
    path = tmp_path / "index.json"
    idx = LocalIndex(path)
    idx.update("a.txt", b"hello", "etag-1")
    idx.save()

    reloaded = LocalIndex(path)
    assert reloaded.is_changed("a.txt", b"hello") is False


def test_remove_forgets_the_file(tmp_path):
    idx = LocalIndex(tmp_path / "index.json")
    idx.update("a.txt", b"hello", "etag-1")
    idx.remove("a.txt")
    assert idx.is_changed("a.txt", b"hello") is True
    assert "a.txt" not in idx.known_paths()


def test_known_paths_tracks_all_files(tmp_path):
    idx = LocalIndex(tmp_path / "index.json")
    idx.update("a.txt", b"1", "etag-a")
    idx.update("b.txt", b"2", "etag-b")
    assert idx.known_paths() == {"a.txt", "b.txt"}


def test_content_hash_is_sha256():
    import hashlib
    assert LocalIndex.content_hash(b"hello") == hashlib.sha256(b"hello").hexdigest()


def test_etag_round_trips_with_content(tmp_path):
    path = tmp_path / "index.json"
    idx = LocalIndex(path)
    idx.update("a.txt", b"hello", "etag-1")
    idx.save()
    reloaded = LocalIndex(path)
    assert reloaded.etag("a.txt") == "etag-1"          # base for the next commit survives reload
    assert reloaded.is_changed("a.txt", b"hello") is False  # content still recognized


def test_etag_of_an_unknown_path_is_none(tmp_path):
    # a brand-new file has no base -> commit sends If-None-Match: * (create)
    idx = LocalIndex(tmp_path / "index.json")
    assert idx.etag("never-seen.txt") is None
