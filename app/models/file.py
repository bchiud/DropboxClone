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
