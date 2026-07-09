from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.application.auth_service import AuthService, InvalidCredentials, UsernameTaken
from app.dependencies import get_auth_service
from app.models.user import TokenResponse, User, UserRegisterRequest, UserRegisterResponse

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
        token: str = auth_service.authenticate(form.username.lower(), form.password)
    except InvalidCredentials:
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(access_token=token).model_dump()
