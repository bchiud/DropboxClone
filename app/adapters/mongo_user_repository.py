from typing import Any, Mapping

from pymongo.synchronous.collection import Collection

from app.models.user import User
from app.ports.user_repository import UserRepository


class MongoUserRepository(UserRepository):

    def __init__(self, collection: Collection):
        self._collection = collection

    def get_by_username(self, username: str) -> User | None:
        doc: Mapping[str, Any] | None | Any = self._collection.find_one(filter={"username": username})
        return User(**doc) if doc else None

    def save(self, user: User) -> None:
        self._collection.replace_one(
            filter={"username": user.username},
            replacement=user.model_dump(),
            upsert=True,
        )
