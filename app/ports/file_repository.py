from abc import ABC, abstractmethod


class FileRepository(ABC):
    @abstractmethod
    def save(self, doc: dict) -> None: ...

    @abstractmethod
    def get(self, owner: str, path: str) -> dict | None: ...

    @abstractmethod
    def list_for_owner(self, owner: str) -> list[dict]: ...
