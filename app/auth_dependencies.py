"""Web-layer auth dependencies.

Kept separate from dependencies.py (pure composition) because these are
HTTP-coupled: they read the Authorization header and raise HTTPException.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.domain import security

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    """Decode the bearer token and return the authenticated username."""
    username = security.decode_access_token(token)
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return username
