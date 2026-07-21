from abc import ABC, abstractmethod


class BlockIndex(ABC):
    @abstractmethod
    def present_subset(self, owner: str, hashes: list[str]) -> set[str]: ...

    @abstractmethod
    def add_many(self, owner: str, hashes: list[str]) -> None: ...
