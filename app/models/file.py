from datetime import datetime

from pydantic import BaseModel

from app.models.types import RootedPath


class FileBase(BaseModel):
    owner: str
    path: RootedPath
    size: int
    updated_at: datetime


class FileSummary(FileBase):
    pass


class FileRecord(FileBase):
    block_hashes: list[str]


class BlockHashesRequest(BaseModel):
    hashes: list[str]


class CommitFileRequest(BaseModel):
    path: RootedPath
    size: int
    block_hashes: list[str]
