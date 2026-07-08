import datetime

from app.domain import chunker
from app.models.file import FileRecord, FileSummary
from app.ports.block_store import BlockStore
from app.ports.file_repository import FileRepository


class FileService:
    def __init__(self, block_store: BlockStore, file_repository: FileRepository) -> None:
        self._block_store = block_store
        self._file_repository = file_repository

    def save_file(self, owner, path, data: bytes) -> FileRecord:
        blocks: list[tuple[str, bytes]] = list(chunker.split(data))
        for h, block in blocks:
            self._block_store.put_block(h, block)
        block_hashes: list[str] = [h for h, _ in blocks]
        record: FileRecord = FileRecord(
            owner=owner,
            path=path,
            size=len(data),
            block_hashes=block_hashes,
            updated_at=datetime.datetime.now(datetime.UTC),
        )
        self._file_repository.save(record)
        return record

    def load_file(self, owner: str, path: str) -> bytes:
        record: FileRecord = self._file_repository.get(owner, path)
        if record is None:
            raise FileNotFoundError(f"{owner}:{path}")
        block: list[bytes] = [self._block_store.get_block(h) for h in record.block_hashes]
        return b"".join(block)

    def list_files(self, owner: str) -> list[FileSummary]:
        return self._file_repository.list_for_owner(owner)
