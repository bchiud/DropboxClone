from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.application.auth_service import AuthService, InvalidCredentials, InvalidRefreshToken, UsernameTaken
from app.dependencies import get_auth_service
from app.models.user import (
    AccessTokenResponse, RefreshRequest, TokenResponse, User, UserRegisterRequest,
    UserRegisterResponse,
)

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


@router.post(
    "/register",
    response_model=UserRegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_user(
        user_request: UserRegisterRequest,
        auth_service: AuthService = Depends(get_auth_service),
):
    try:
        user: User = auth_service.register(user_request.username.lower(), user_request.password)
    except UsernameTaken:
        raise HTTPException(status_code=409, detail=f"Username={user_request.username} already exists")
    return user


@router.post("/login", response_model=TokenResponse)
def login_user(
        form: OAuth2PasswordRequestForm = Depends(),
        auth_service: AuthService = Depends(get_auth_service),
):
    try:
        access, refresh = auth_service.authenticate(form.username.lower(), form.password)
    except InvalidCredentials:
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(access_token=access, refresh_token=refresh).model_dump()


@router.post("/refresh", response_model=AccessTokenResponse)
def refresh_access_token(
        body: RefreshRequest,
        auth_service: AuthService = Depends(get_auth_service),
):
    try:
        access = auth_service.refresh(body.refresh_token)
    except InvalidRefreshToken:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return AccessTokenResponse(access_token=access).model_dump()


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
        body: RefreshRequest,
        auth_service: AuthService = Depends(get_auth_service),
):
    auth_service.logout(body.refresh_token)
