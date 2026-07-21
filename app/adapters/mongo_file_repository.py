from typing import Any, Mapping

from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError
from pymongo.results import DeleteResult
from pymongo.synchronous.cursor import Cursor

from app.models.file import FileRecord, FileSummary
from app.ports.file_repository import FileRepository, VersionConflict


class MongoFileRepository(FileRepository):
    def __init__(self, collection: Collection):
        self._collection = collection
        self._collection.create_index([("owner", 1), ("path", 1)], unique=True)

    def save(self, record: FileRecord, expected_etag: str | None) -> None:
        if expected_etag is None:  # new file
            try:
                self._collection.insert_one(record.model_dump())
            except DuplicateKeyError:
                existing = self._collection.find_one({"owner": record.owner, "path": record.path})
                if existing is None or existing["etag"] != record.etag:
                    raise VersionConflict
            return
        result = self._collection.replace_one(
            filter={
                "owner": record.owner,
                "path": record.path,
                "etag": {"$in": [
                    expected_etag,  # not updated yet
                    record.etag,  # already updated. this call may be a retry or parallel update from another client
                ]}
            },
            replacement=record.model_dump(),
            upsert=False,
        )
        if result.matched_count == 0:
            raise VersionConflict

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
