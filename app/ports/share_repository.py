from abc import ABC, abstractmethod

from app.models.share import Share


class ShareRepository(ABC):
    @abstractmethod
    def add(self, share: Share) -> None: ...

    @abstractmethod
    def remove(self, owner: str, path: str, shared_with: str) -> None: ...

    @abstractmethod
    def remove_all_for_path(self, owner: str, path: str) -> int: ...

    @abstractmethod
    def exists(self, owner: str, path: str, shared_with: str) -> bool: ...

    @abstractmethod
    def list_for_recipient(self, username: str) -> list[Share]: ...

    @abstractmethod
    def list_for_owner(self, owner: str) -> list[Share]: ...