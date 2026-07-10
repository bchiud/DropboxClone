from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.models.types import RootedPath


class Share(BaseModel):
    owner: str
    path: RootedPath
    shared_with: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ShareRequest(BaseModel):
    path: RootedPath
    shared_with: str


class ShareLink(BaseModel):
    jti: str
    owner: str
    path: RootedPath
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime


class ShareLinkRequest(BaseModel):
    path: RootedPath
