import hashlib


def recipe_etag(block_hashes: list[str]) -> str:
    return hashlib.sha256("\n".join(block_hashes).encode()).hexdigest()
