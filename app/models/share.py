from datetime import UTC, datetime

from pydantic import BaseModel, Field


class Share(BaseModel):
    owner: str
    path: str
    shared_with: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ShareRequest(BaseModel):
    path: str
    shared_with: str


class ShareLink(BaseModel):
    jti: str
    owner: str
    path: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime


class ShareLinkRequest(BaseModel):
    path: str
