"""Local sync index.

Remembers, per file, the last-synced content hash (to detect what actually
changed and skip unchanged files) and the server's etag as of that sync (the
base precondition for the next commit). Persisted to a JSON file.

On-disk format: {rel_path: {"content": <sha256>, "etag": <etag|null>}}. This
supersedes the earlier {rel_path: <sha256>} shape — an old index won't load;
delete it and re-sync.
"""
import hashlib
import json
from pathlib import Path


class LocalIndex:
    def __init__(self, index_path: Path):
        self._index_path = index_path
        self._hashes: dict[str, dict[str, str]] = {}  # rel_path -> {"content": sha256, "etag": etag}
        self._load()

    def _load(self) -> None:
        if self._index_path.exists():
            self._hashes = json.loads(self._index_path.read_text())

    def save(self) -> None:
        self._index_path.write_text(json.dumps(self._hashes, indent=2))

    @staticmethod
    def content_hash(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def is_changed(self, rel_path: str, data: bytes) -> bool:
        return self._hashes.get(rel_path, {}).get("content") != self.content_hash(data)

    def update(self, rel_path: str, data: bytes, etag: str | None) -> None:
        self._hashes[rel_path] = {"content": self.content_hash(data), "etag": etag}

    def remove(self, rel_path: str) -> None:
        self._hashes.pop(rel_path, None)

    def known_paths(self) -> set[str]:
        return set(self._hashes)

    def etag(self, rel_path: str) -> str | None:
        return self._hashes.get(rel_path, {}).get("etag")  # None => unknown/new => create
