from typing import Any, Mapping

from pymongo.collection import Collection
from pymongo.results import DeleteResult
from pymongo.synchronous.cursor import Cursor

from app.models.file import FileRecord, FileSummary
from app.ports.file_repository import FileRepository


class MongoFileRepository(FileRepository):
    def __init__(self, collection: Collection):
        self._collection = collection

    def save(self, record: FileRecord) -> None:
        self._collection.replace_one(
            filter={"owner": record.owner, "path": record.path},
            replacement=record.model_dump(),
            upsert=True,
        )  # upsert for now. will do versioning later

    def get(self, owner: str, path: str) -> FileRecord | None:
        doc: Mapping[str, Any] | None | Any = self._collection.find_one(filter={"owner": owner, "path": path})
        return FileRecord(**doc) if doc else None

    def delete(self, owner: str, path: str) -> bool:
        result: DeleteResult = self._collection.delete_one(filter={"owner": owner, "path": path})
        return result.deleted_count > 0

    def list_for_owner(self, owner: str) -> list[FileSummary]:
        docs: Cursor = self._collection.find(
            {"owner": owner},
            {"_id": 0, "block_hashes": 0},
        )
        return [FileSummary(**doc) for doc in docs]
