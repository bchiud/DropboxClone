from abc import ABC, abstractmethod

from app.models.file import FileRecord, FileSummary


class FileRepository(ABC):
    @abstractmethod
    def save(self, doc: FileRecord) -> None: ...

    @abstractmethod
    def get(self, owner: str, path: str) -> FileRecord | None: ...

    @abstractmethod
    def delete(self, owner: str, path: str) -> bool: ...

    @abstractmethod
    def list_for_owner(self, owner: str) -> list[FileSummary]: ...
