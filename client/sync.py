"""The sync engine: reconcile a local folder with the server.

push()  local -> server : upload files whose content changed since last sync
pull()  server -> local : download files that are missing or differ locally

The LocalIndex (last-synced content hash per path) is the memory that makes
"what changed?" answerable without re-transferring everything.

Limitations (v1, deliberately simple):
- Change detection on pull downloads each file to compare — a server-side
  content fingerprint in the listing would let us skip unchanged downloads.
- No conflict resolution: if a file changed both locally and remotely, this is
  last-writer-wins. Conflict copies are future work.
"""
from pathlib import Path

from client.api_client import ApiClient
from client.state import LocalIndex


class SyncEngine:
    def __init__(self, api: ApiClient, index: LocalIndex, folder: Path):
        self._api = api
        self._index = index
        self._folder = folder

    # --- path mapping: local Path <-> server "/posix/path" ---
    def _server_path(self, file: Path) -> str:
        return "/" + file.relative_to(self._folder).as_posix()

    def _local_path(self, server_path: str) -> Path:
        return self._folder / server_path.lstrip("/")

    # --- push: local -> server ---
    def push(self) -> list[str]:
        pushed: list[str] = []
        for file in sorted(self._folder.rglob("*")):
            if not file.is_file():
                continue
            server_path = self._server_path(file)
            data = file.read_bytes()
            if self._index.is_changed(server_path, data):
                self._api.upload(server_path, data)
                self._index.update(server_path, data)
                pushed.append(server_path)
        self._index.save()
        return pushed

    # --- pull: server -> local ---
    def pull(self) -> list[str]:
        pulled: list[str] = []
        for summary in self._api.list_files():
            server_path = summary["path"]
            data = self._api.download(server_path)
            local = self._local_path(server_path)
            if not local.exists() or self._index.is_changed(server_path, data):
                local.parent.mkdir(parents=True, exist_ok=True)
                local.write_bytes(data)
                self._index.update(server_path, data)
                pulled.append(server_path)
        self._index.save()
        return pulled

    def sync(self) -> dict[str, list[str]]:
        # push first so local edits win over an identical-but-older remote,
        # then pull to bring down anything new from other devices.
        pushed = self.push()
        pulled = self.pull()
        return {"pushed": pushed, "pulled": pulled}
