import hashlib
from typing import Iterator

BLOCK_SIZE = 4 * 1024 * 1024  # match server's block size: 4 MiB


def hash_block(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def split(data: bytes, block_size: int = BLOCK_SIZE) -> Iterator[tuple[str, bytes]]:
    for i in range(0, len(data), block_size):
        block = data[i:i + block_size]
        yield hash_block(block), block
