from typing import Any, Mapping

from pymongo.errors import DuplicateKeyError
from pymongo.synchronous.collection import Collection

from app.models.user import User
from app.ports.user_repository import UserRepository, UsernameAlreadyExists


class MongoUserRepository(UserRepository):

    def __init__(self, collection: Collection):
        self._collection = collection
        self._collection.create_index("username", unique=True)

    def get_by_username(self, username: str) -> User | None:
        doc: Mapping[str, Any] | None | Any = self._collection.find_one(filter={"username": username})
        return User(**doc) if doc else None

    def save(self, user: User) -> None:
        try:
            self._collection.insert_one(user.model_dump())
        except DuplicateKeyError:
            raise UsernameAlreadyExists(user.username)
