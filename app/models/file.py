from datetime import datetime

from pydantic import BaseModel

from app.models.types import RootedPath


class FileBase(BaseModel):
    owner: str
    path: RootedPath
    size: int
    updated_at: datetime


class FileSummary(FileBase):
    etag: str


class FileRecord(FileBase):
    block_hashes: list[str]
    etag: str


class BlockHashesRequest(BaseModel):
    hashes: list[str]


class CommitFileRequest(BaseModel):
    path: RootedPath
    size: int
    block_hashes: list[str]
