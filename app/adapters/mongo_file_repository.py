from pymongo.collection import Collection
from pymongo.synchronous.cursor import Cursor

from app.ports.file_repository import FileRepository


class MongoFileRepository(FileRepository):
    def __init__(self, collection: Collection):
        self._collection = collection

    def save(self, doc: dict) -> None:
        query = {"owner": doc["owner"], "path": doc["path"]}
        self._collection.replace_one(
            filter=query, replacement=doc, upsert=True,
        )  # upsert for now. will do versioning later

    def get(self, owner: str, path: str) -> dict | None:
        query: dict = {"owner": owner, "path": path}
        return self._collection.find_one(filter=query)

    def list_for_owner(self, owner: str) -> list[dict]:
        docs: Cursor = self._collection.find(
            {"owner": owner},
            {"_id": 0, "block_hashes": 0},
        )
        return list(docs)
