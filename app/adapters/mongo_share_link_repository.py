from pymongo.synchronous.collection import Collection
from pymongo.synchronous.cursor import Cursor

from app.models.share import ShareLink
from app.ports.share_link_repository import ShareLinkRepository


class MongoShareLinkRepository(ShareLinkRepository):
    def __init__(self, collection: Collection) -> None:
        self._collection = collection
        self._collection.create_index("jti", unique=True)
        self._collection.create_index([("owner", 1), ("path", 1)])
        self._collection.create_index("expires_at", expireAfterSeconds=0)

    def add(self, link: ShareLink) -> None:
        self._collection.insert_one(link.model_dump())

    def delete(self, owner: str, jti: str) -> None:
        self._collection.delete_one({'owner': owner, 'jti': jti})

    def delete_all_for_path(self, owner: str, path: str) -> int:
        return self._collection.delete_many({'owner': owner, 'path': path}).deleted_count

    def exists(self, jti: str) -> bool:
        return self._collection.find_one({'jti': jti}) is not None

    def list_for_owner(self, owner: str) -> list[ShareLink]:
        docs: Cursor = self._collection.find({'owner': owner}, {"_id": 0})
        return [ShareLink(**doc) for doc in docs]
