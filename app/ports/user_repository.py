from abc import ABC, abstractmethod

from app.models.user import User


class UserRepository(ABC):
    @abstractmethod
    def get_by_username(self, username: str) -> dict | None: ...

    @abstractmethod
    def save(self, user: User) -> None: ...
