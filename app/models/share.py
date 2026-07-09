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



class ShareLinkRequest(BaseModel):
    path: str