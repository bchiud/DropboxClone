import datetime

from app.config import settings
from app.domain import security
from app.domain.security import new_jti
from app.models.user import RefreshToken, User
from app.ports.refresh_token_repository import RefreshTokenRepository
from app.ports.user_repository import UserRepository, UsernameAlreadyExists


class UsernameTaken(Exception):
    pass


class InvalidCredentials(Exception):
    pass


class InvalidRefreshToken(Exception):
    pass


class AuthService:
    def __init__(
            self,
            refresh_token_repository: RefreshTokenRepository,
            user_repository: UserRepository,
    ):
        self._refresh_token_repository = refresh_token_repository
        self._user_repository = user_repository

    def register(self, username: str, password: str) -> User:
        if self._user_repository.get_by_username(username) is not None:
            raise UsernameTaken(username)
        user = User(
            username=username,
            password_hash=security.hash_password(password),
            created_at=datetime.datetime.now(datetime.UTC),
        )
        try:
            self._user_repository.save(user)
        except UsernameAlreadyExists:
            raise UsernameTaken(username)
        return user

    def authenticate(self, username: str, password: str) -> tuple[str, str]:
        user = self._user_repository.get_by_username(username)
        if user is None or not security.verify_password(password, user.password_hash):
            raise InvalidCredentials()
        return self._issue_tokens(user.username)

    def _issue_tokens(self, username: str) -> tuple[str, str]:
        now = datetime.datetime.now(datetime.UTC)
        expires_at = now + datetime.timedelta(
            minutes=settings.refresh_token_expire_minutes,
        )
        jti = new_jti()
        access = security.create_access_token(username)
        refresh = security.create_refresh_token(username, jti, expires_at)
        self._refresh_token_repository.add(
            RefreshToken(
                jti=jti,
                username=username,
                created_at=now,
                expires_at=expires_at,
            ),
        )
        return access, refresh

    def refresh(self, refresh_token: str) -> str:
        decoded = security.decode_refresh_token(refresh_token)
        if decoded is None:
            raise InvalidRefreshToken()
        username, jti = decoded
        if not self._refresh_token_repository.exists(jti):
            raise InvalidRefreshToken()  # revoked, or expired + TTL-reaped
        return security.create_access_token(username)

    def logout(self, refresh_token: str) -> None:
        decoded = security.decode_refresh_token(refresh_token)
        if decoded is None:
            return  # already unusable — logout is idempotent
        _, jti = decoded
        self._refresh_token_repository.delete(jti)
