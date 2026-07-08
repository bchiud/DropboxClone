"""Unit tests for the client-side LocalIndex."""
from client.state import LocalIndex


def test_new_file_is_changed(tmp_path):
    idx = LocalIndex(tmp_path / "index.json")
    assert idx.is_changed("a.txt", b"hello") is True  # never seen


def test_unchanged_file_is_not_changed(tmp_path):
    idx = LocalIndex(tmp_path / "index.json")
    idx.update("a.txt", b"hello")
    assert idx.is_changed("a.txt", b"hello") is False


def test_edited_file_is_changed(tmp_path):
    idx = LocalIndex(tmp_path / "index.json")
    idx.update("a.txt", b"hello")
    assert idx.is_changed("a.txt", b"hello world") is True


def test_persists_across_reload(tmp_path):
    path = tmp_path / "index.json"
    idx = LocalIndex(path)
    idx.update("a.txt", b"hello")
    idx.save()

    reloaded = LocalIndex(path)
    assert reloaded.is_changed("a.txt", b"hello") is False


def test_remove_forgets_the_file(tmp_path):
    idx = LocalIndex(tmp_path / "index.json")
    idx.update("a.txt", b"hello")
    idx.remove("a.txt")
    assert idx.is_changed("a.txt", b"hello") is True
    assert "a.txt" not in idx.known_paths()


def test_known_paths_tracks_all_files(tmp_path):
    idx = LocalIndex(tmp_path / "index.json")
    idx.update("a.txt", b"1")
    idx.update("b.txt", b"2")
    assert idx.known_paths() == {"a.txt", "b.txt"}


def test_content_hash_is_sha256():
    import hashlib
    assert LocalIndex.content_hash(b"hello") == hashlib.sha256(b"hello").hexdigest()
