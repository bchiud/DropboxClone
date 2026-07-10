from abc import ABC, abstractmethod


class BlockStore(ABC):
    """Block metadata only. Block *bytes* never pass through the app server —
    the client PUTs/GETs them straight to storage with a presigned url."""

    @abstractmethod
    def has_block(self, block_hash: str) -> bool: ...

    @abstractmethod
    def presigned_put_url(self, block_hash: str) -> str: ...

    @abstractmethod
    def presigned_get_url(self, block_hash: str) -> str: ...
