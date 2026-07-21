import datetime

from app.domain.recipe import recipe_etag
from app.models.file import FileRecord, FileSummary
from app.ports.block_index import BlockIndex
from app.ports.block_store import BlockStore
from app.ports.file_repository import FileRepository


class BlockNotInFile(Exception):
    def __init__(self, hashes: list[str]):
        self.hashes = hashes


class MissingBlocks(Exception):
    def __init__(self, hashes: list[str]):
        self.hashes = hashes


class FileService:
    @staticmethod
    def _block_key(owner: str, block_hash: str) -> str:
        return f"{owner}/{block_hash}"

    def __init__(self, block_store: BlockStore, file_repository: FileRepository, block_index: BlockIndex) -> None:
        self._block_store = block_store
        self._file_repository = file_repository
        self._block_index = block_index

    def list_files(self, owner: str) -> list[FileSummary]:
        return self._file_repository.list_for_owner(owner)

    def missing_blocks(self, owner: str, hashes: list[str]) -> list[str]:
        present = self._block_index.present_subset(owner, hashes)
        return [h for h in hashes if h not in present]

    def upload_urls(self, owner: str, hashes: list[str]) -> dict[str, str]:
        return {
            h: self._block_store.presigned_put_url(self._block_key(owner, h))
            for h in hashes
        }

    def download_urls(self, owner: str, path: str, hashes: list[str]) -> dict[str, str]:
        recipe: FileRecord = self.get_recipe(owner, path)
        extra_hashes: list[str] = [h for h in hashes if h not in set(recipe.block_hashes)]
        if extra_hashes:
            raise BlockNotInFile(extra_hashes)
        return {
            h: self._block_store.presigned_get_url(self._block_key(owner, h))
            for h in hashes
        }

    def commit_file(self, owner: str, path: str, size: int, block_hashes: list[str],
                    expected_etag: str | None) -> FileRecord:
        present = self._block_index.present_subset(owner, block_hashes)
        new = [h for h in block_hashes if h not in present]
        absent = [h for h in new if not self._block_store.has_block(self._block_key(owner, h))]
        if absent:
            raise MissingBlocks(absent)
        if new:
            self._block_index.add_many(owner, new)

        fileRecord = FileRecord(
            owner=owner,
            path=path,
            size=size,
            block_hashes=block_hashes,
            updated_at=datetime.datetime.now(datetime.UTC),
            etag=recipe_etag(block_hashes),
        )
        self._file_repository.save(fileRecord, expected_etag)
        return fileRecord

    def delete_file(self, owner: str, path: str) -> None:
        if not self._file_repository.delete(owner, path):
            raise FileNotFoundError(f"{owner}:{path}")

    def get_recipe(self, owner: str, path: str) -> FileRecord:
        fileRecord: FileRecord = self._file_repository.get(owner, path)
        if fileRecord is None:
            raise FileNotFoundError(f"{owner}:{path}")
        return fileRecord
