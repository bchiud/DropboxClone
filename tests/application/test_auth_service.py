"""Unit tests for AuthService — the auth use-case orchestrator.

The user repository is replaced with an in-memory fake.
"""
import pytest

from app.application.auth_service import (
    AuthService,
    InvalidCredentials,
    UsernameTaken,
)
from app.domain import security
from app.models.user import User
from app.ports.user_repository import UserRepository, UsernameAlreadyExists


class FakeUserRepository(UserRepository):
    def __init__(self):
        self.users: dict[str, User] = {}

    def get_by_username(self, username):
        return self.users.get(username)

    def save(self, user: User):
        self.users[user.username] = user


@pytest.fixture
def auth():
    return AuthService(FakeUserRepository())


def test_register_creates_hashed_user(auth):
    user = auth.register("alice", "secret123")
    assert isinstance(user, User)
    assert user.username == "alice"
    assert user.password_hash != "secret123"
    assert security.verify_password("secret123", user.password_hash)


def test_register_duplicate_username_raises(auth):
    auth.register("alice", "x")
    with pytest.raises(UsernameTaken):
        auth.register("alice", "y")


def test_register_translates_repo_duplicate_into_username_taken():
    # Race path: the pre-check passes (get returns None), but the repo's insert
    # loses the race and raises UsernameAlreadyExists (the unique index firing).
    # The service must map that to the same UsernameTaken the caller expects.
    class RacingRepo(FakeUserRepository):
        def save(self, user: User):
            raise UsernameAlreadyExists(user.username)

    auth = AuthService(RacingRepo())
    with pytest.raises(UsernameTaken):
        auth.register("alice", "x")


def test_authenticate_valid_returns_token(auth):
    auth.register("alice", "secret123")
    token = auth.authenticate("alice", "secret123")
    assert security.decode_access_token(token) == "alice"


def test_authenticate_wrong_password_raises(auth):
    auth.register("alice", "secret123")
    with pytest.raises(InvalidCredentials):
        auth.authenticate("alice", "wrong")


def test_authenticate_unknown_user_raises_same_error(auth):
    # Enumeration defense: unknown user and wrong password are indistinguishable.
    with pytest.raises(InvalidCredentials):
        auth.authenticate("nobody", "whatever")
