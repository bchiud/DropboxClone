from pymongo.synchronous.collection import Collection
from pymongo.synchronous.cursor import Cursor

from app.models.share import Share
from app.ports.share_repository import ShareRepository


class MongoShareRepository(ShareRepository):
    def __init__(self, collection: Collection) -> None:
        self._collection = collection

    def add(self, share: Share) -> None:
        self._collection.replace_one(
            filter={"owner": share.owner, "path": share.path, "shared_with": share.shared_with},
            replacement=share.model_dump(),
            upsert=True,
        )

    def remove(self, owner: str, path: str, shared_with: str) -> None:
        self._collection.delete_one(filter={"owner": owner, "path": path, "shared_with": shared_with})

    def exists(self, owner: str, path: str, shared_with: str) -> bool:
        return self._collection.find_one(filter={"owner": owner, "path": path, "shared_with": shared_with}) is not None

    def list_for_recipient(self, username: str) -> list[Share]:
        docs: Cursor = self._collection.find({"shared_with": username}, {"_id": 0})
        return [Share(**doc) for doc in docs]

    def list_for_owner(self, owner: str) -> list[Share]:
        docs: Cursor = self._collection.find({"owner": owner}, {"_id": 0})
        return [Share(**doc) for doc in docs]
