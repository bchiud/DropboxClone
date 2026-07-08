import datetime

from app.models.file import FileRecord, FileSummary
from app.ports.block_store import BlockStore
from app.ports.file_repository import FileRepository


class MissingBlocks(Exception):
    def __init__(self, hashes: list[str]):
        self.hashes = hashes


class FileService:
    @staticmethod
    def _block_key(owner: str, block_hash: str) -> str:
        return f"{owner}/{block_hash}"

    def __init__(self, block_store: BlockStore, file_repository: FileRepository) -> None:
        self._block_store = block_store
        self._file_repository = file_repository

    def list_files(self, owner: str) -> list[FileSummary]:
        return self._file_repository.list_for_owner(owner)

    def missing_blocks(self, owner: str, hashes: list[str]) -> list[str]:
        return [
            h for h in hashes
            if not self._block_store.has_block(self._block_key(owner, h))
        ]

    def upload_urls(self, owner: str, hashes: list[str]) -> dict[str, str]:
        return {
            h: self._block_store.presigned_put_url(self._block_key(owner, h))
            for h in hashes
        }

    def download_urls(self, owner: str, hashes: list[str]) -> dict[str, str]:
        return {
            h: self._block_store.presigned_get_url(self._block_key(owner, h))
            for h in hashes
        }

    def commit_file(
            self, owner: str, path: str, size: int,
            block_hashes: list[str],
    ) -> FileRecord:
        missing = self.missing_blocks(owner, block_hashes)
        if missing:
            raise MissingBlocks(missing)

        fileRecord = FileRecord(
            owner=owner,
            path=path,
            size=size,
            block_hashes=block_hashes,
            updated_at=datetime.datetime.now(datetime.UTC),
        )
        self._file_repository.save(fileRecord)
        return fileRecord

    def get_recipe(self, owner: str, path: str) -> FileRecord:
        fileRecord: FileRecord = self._file_repository.get(owner, path)
        if fileRecord is None:
            raise FileNotFoundError(f"{owner}:{path}")
        return fileRecord
