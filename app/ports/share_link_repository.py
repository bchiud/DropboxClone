from abc import ABC, abstractmethod

from app.models.share import ShareLink


class ShareLinkRepository(ABC):
    @abstractmethod
    def add(self, link: ShareLink) -> None: ...

    @abstractmethod
    def delete(self, owner: str, jti: str) -> None: ...

    @abstractmethod
    def delete_all_for_path(self, owner: str, path: str) -> int: ...

    @abstractmethod
    def exists(self, jti: str) -> bool: ...

    @abstractmethod
    def list_for_owner(self, owner: str) -> list[ShareLink]: ...
