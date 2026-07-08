from datetime import datetime

from pydantic import BaseModel


class FileBase(BaseModel):
    owner: str
    path: str
    size: int
    updated_at: datetime


class FileSummary(FileBase):
    pass


class FileRecord(FileBase):
    block_hashes: list[str]


class BlockHashesRequest(BaseModel):
    hashes: list[str]


class CommitFileRequest(BaseModel):
    path: str
    size: int
    block_hashes: list[str]
