import datetime

import bcrypt
import jwt

from app.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_access_token(subject: str) -> str:
    now = datetime.datetime.now(datetime.UTC)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + datetime.timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload.get("sub")
    except jwt.InvalidTokenError:
        return None


def create_share_token(owner: str, path: str, jti: str, expires_at: datetime.datetime) -> str:
    payload = {
        "typ": "share",
        "owner": owner,
        "path": path,
        "jti": jti,
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_share_token(token: str) -> tuple[str, str, str] | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.InvalidTokenError:
        return None
    if payload.get("typ") != "share":
        return None
    return payload["owner"], payload["path"], payload["jti"]
