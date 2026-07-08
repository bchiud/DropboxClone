from abc import ABC, abstractmethod


class BlockStore(ABC):
    @abstractmethod
    def has_block(self, block_hash: str) -> bool: ...

    @abstractmethod
    def put_block(self, block_hash: str, data: bytes) -> None: ...

    @abstractmethod
    def get_block(self, block_hash: str) -> bytes: ...

    @abstractmethod
    def presigned_put_url(self, block_hash: str) -> str: ...

    @abstractmethod
    def presigned_get_url(self, block_hash: str) -> str: ...
