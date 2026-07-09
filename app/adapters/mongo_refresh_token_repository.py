from pymongo.collection import Collection

from app.models.user import RefreshToken
from app.ports.refresh_token_repository import RefreshTokenRepository


class MongoRefreshTokenRepository(RefreshTokenRepository):
    def __init__(self, collection: Collection) -> None:
        self._collection = collection
        self._collection.create_index("jti", unique=True)
        self._collection.create_index("expires_at", expireAfterSeconds=0)  # TTL auto-reap

    def add(self, token: RefreshToken) -> None:
        self._collection.insert_one(token.model_dump())

    def exists(self, jti: str) -> bool:
        return self._collection.find_one({"jti": jti}) is not None

    def delete(self, jti: str) -> None:
        self._collection.delete_one({"jti": jti})
