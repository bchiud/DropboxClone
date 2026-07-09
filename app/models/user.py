from datetime import datetime

from pydantic import BaseModel


class UserBase(BaseModel):
    username: str


class User(UserBase):
    password_hash: str
    created_at: datetime


class UserRegisterRequest(UserBase):
    password: str


class UserRegisterResponse(UserBase):
    created_at: datetime


class RefreshToken(BaseModel):
    jti: str
    username: str
    created_at: datetime
    expires_at: datetime


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
