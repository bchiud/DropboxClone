"""The sync engine: reconcile a local folder with the server via delta sync.

push()  local -> server : chunk each changed file, upload only the blocks the
                          server is missing (straight to B2), then commit the recipe.
pull()  server -> local : fetch the recipe, download its blocks (straight from B2,
                          re-verifying each), reassemble.

Only changed *blocks* cross the network, and file bytes never pass through the
app server — they go directly to/from object storage via presigned URLs.

Limitations (v1): pull downloads a differing file's blocks in full (no local
block reuse); last-writer-wins (no conflict copies).
"""
from pathlib import Path

from client import chunker
from client.api_client import ApiClient
from client.state import LocalIndex


class CorruptBlock(Exception):
    """A downloaded block's bytes don't match its hash (re-verify failed)."""


class UnsafePath(ValueError):
    """A server-supplied path resolves outside the sync folder."""


class SyncEngine:
    def __init__(self, api: ApiClient, index: LocalIndex, folder: Path):
        self._api = api
        self._index = index
        self._folder = folder

    def _server_path(self, file: Path) -> str:
        return "/" + file.relative_to(self._folder).as_posix()

    def _local_path(self, server_path: str) -> Path:
        # lstrip: an absolute right-hand side would discard the folder entirely.
        # resolve: a symlinked component can escape a path that reads as canonical.
        root = self._folder.resolve()
        local = (root / server_path.lstrip("/")).resolve()
        if not local.is_relative_to(root):
            raise UnsafePath(f"path escapes the sync folder: {server_path!r}")
        if local == root:
            raise UnsafePath(f"path resolves to the sync folder itself: {server_path!r}")
        return local

    # --- push: chunk -> negotiate -> upload only missing blocks -> commit ---
    def push(self) -> list[str]:
        pushed: list[str] = []
        for file in sorted(self._folder.rglob("*")):
            if not file.is_file():
                continue
            server_path = self._server_path(file)
            data = file.read_bytes()
            if not self._index.is_changed(server_path, data):
                continue

            blocks = list(chunker.split(data))
            hashes = [h for h, _ in blocks]
            block_bytes = dict(blocks)  # hash -> bytes

            missing = self._api.missing_blocks(hashes)
            if missing:
                urls = self._api.upload_urls(missing)
                for h in missing:
                    self._api.put_block(urls[h], block_bytes[h])  # -> B2 directly

            self._api.commit_file(server_path, len(data), hashes)
            self._index.update(server_path, data)
            pushed.append(server_path)
        self._index.save()
        return pushed

    # --- pull: recipe -> download blocks (verify) -> reassemble ---
    def pull(self) -> list[str]:
        pulled: list[str] = []
        for summary in self._api.list_files():
            server_path = summary["path"]
            recipe = self._api.get_recipe(server_path)
            hashes = recipe["block_hashes"]
            local = self._local_path(server_path)

            # skip download if local content already matches the recipe
            if local.exists():
                local_hashes = [h for h, _ in chunker.split(local.read_bytes())]
                if local_hashes == hashes:
                    continue

            # (re-)downloads whole file
            # in ideal case, implement content-defined chunking, and pull delta blocks only
            data = self._download_blocks(hashes)
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(data)
            self._index.update(server_path, data)
            pulled.append(server_path)
        self._index.save()
        return pulled

    def _download_blocks(self, hashes: list[str]) -> bytes:
        urls = self._api.download_urls(hashes)
        parts: list[bytes] = []
        for h in hashes:
            block = self._api.get_block(urls[h])  # <- from B2 directly
            if chunker.hash_block(block) != h:  # re-verify on read
                raise CorruptBlock(h)
            parts.append(block)
        return b"".join(parts)

    def sync(self) -> dict[str, list[str]]:
        return {"pushed": self.push(), "pulled": self.pull()}
