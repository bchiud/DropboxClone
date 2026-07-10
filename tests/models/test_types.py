"""Unit tests for app/models/types.py — the RootedPath constraint."""
import unicodedata

import pytest

from app.models.types import _must_be_rooted


@pytest.mark.parametrize("path", ["/foo.txt", "/docs/a.txt", "/a/b/c.bin"])
def test_accepts_rooted_paths(path):
    assert _must_be_rooted(path) == path


@pytest.mark.parametrize(
    "path",
    [
        "foo.txt",  # not rooted
        "/../etc/passwd",  # traversal
        "//a",  # empty segment
        "/a//b",
        "/a/",  # trailing slash
        "/",  # no filename
        "/a/./b",  # current-dir segment
        "/a\\b",  # windows separator
        "/a\0b",  # NUL
    ],
)
def test_rejects_malformed_paths(path):
    with pytest.raises(ValueError):
        _must_be_rooted(path)


def test_rejection_message_names_the_offending_path():
    with pytest.raises(ValueError, match=r"/\.\./etc/passwd"):
        _must_be_rooted("/../etc/passwd")


def test_normalizes_nfd_to_nfc():
    nfd = "/" + unicodedata.normalize("NFD", "café.txt")
    nfc = "/" + unicodedata.normalize("NFC", "café.txt")
    assert nfd != nfc  # same filename, different code points
    assert _must_be_rooted(nfd) == nfc
