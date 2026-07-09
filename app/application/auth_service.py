import datetime

from app.domain import security
from app.models.user import User
from app.ports.user_repository import UserRepository, UsernameAlreadyExists


class UsernameTaken(Exception):
    pass


class InvalidCredentials(Exception):
    pass


class AuthService:
    def __init__(self, user_repository: UserRepository):
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

    def authenticate(self, username: str, password: str) -> str:
        user = self._user_repository.get_by_username(username)
        if user is None or not security.verify_password(password, user.password_hash):
            raise InvalidCredentials()
        return security.create_access_token(user.username)
