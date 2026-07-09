from abc import ABC, abstractmethod

from app.models.user import RefreshToken


class RefreshTokenRepository(ABC):
    @abstractmethod
    def add(self, token: RefreshToken) -> None: ...

    @abstractmethod
    def exists(self, jti: str) -> bool: ...

    @abstractmethod
    def delete(self, jti: str) -> None: ...
