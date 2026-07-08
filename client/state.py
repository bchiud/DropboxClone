"""Local sync index.

Remembers each file's last-synced content hash, persisted to a JSON file,
so the sync engine can detect what actually changed and avoid re-uploading
unchanged files on every scan.
"""
import hashlib
import json
from pathlib import Path


class LocalIndex:
    def __init__(self, index_path: Path):
        self._index_path = index_path
        self._hashes: dict[str, str] = {}  # relative_path -> content sha256
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
        return self._hashes.get(rel_path) != self.content_hash(data)

    def update(self, rel_path: str, data: bytes) -> None:
        self._hashes[rel_path] = self.content_hash(data)

    def remove(self, rel_path: str) -> None:
        self._hashes.pop(rel_path, None)

    def known_paths(self) -> set[str]:
        return set(self._hashes)
