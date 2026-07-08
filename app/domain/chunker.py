import hashlib
from typing import Iterator

from app.config import settings


def hash_block(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def split(data: bytes) -> Iterator[tuple[str, bytes]]:
    # content based chunking
    # - calculate hash using rolling window
    # - when hash meets mathematical criteria, create chunk
    # - this helps prevent rewriting entire files when only some parts are editied
    # - but need to tune min / max / avg chunk sizes
    # - side note, updating each window's hash is O(1):
    #   because you can algebraically add the entering byte and subtract the leaving byte
    # old file: abcd | efgh | ijkl
    # new file: zabcd | efgh | ijkl
    #
    # fixed block chunking
    # - will rewrite entire file:
    # old file: abcd | efgh | ijkl
    # new file: zabc | defg | hijk | l
    #
    # for simplicity, we use fixed block chunking
    # dropbox uses fixed block
    # backup software uses content based chunking as changes tend to be incremental
    for i in range(0, len(data), settings.block_size):
        block = data[i:i + settings.block_size]
        yield hash_block(block), block