"""Unit tests for AuthService — the auth use-case orchestrator.

The user + refresh-token repositories are replaced with in-memory fakes.
"""
import pytest

from app.application.auth_service import (
    AuthService,
    InvalidCredentials,
    InvalidRefreshToken,
    UsernameTaken,
)
from app.domain import security
from app.models.user import RefreshToken, User
from app.ports.refresh_token_repository import RefreshTokenRepository
from app.ports.user_repository import UserRepository, UsernameAlreadyExists


class FakeUserRepository(UserRepository):
    def __init__(self):
        self.users: dict[str, User] = {}

    def get_by_username(self, username):
        return self.users.get(username)

    def save(self, user: User):
        self.users[user.username] = user


class FakeRefreshTokenRepository(RefreshTokenRepository):
    def __init__(self):
        self.tokens: dict[str, RefreshToken] = {}

    def add(self, token: RefreshToken) -> None:
        self.tokens[token.jti] = token

    def exists(self, jti: str) -> bool:
        return jti in self.tokens

    def delete(self, jti: str) -> None:
        self.tokens.pop(jti, None)


@pytest.fixture
def auth():
    refresh_repo = FakeRefreshTokenRepository()
    service = AuthService(
        user_repository=FakeUserRepository(),
        refresh_token_repository=refresh_repo,
    )
    return service, refresh_repo


# --- registration ---

def test_register_creates_hashed_user(auth):
    svc, _ = auth
    user = svc.register("alice", "secret123")
    assert isinstance(user, User)
    assert user.username == "alice"
    assert user.password_hash != "secret123"
    assert security.verify_password("secret123", user.password_hash)


def test_register_duplicate_username_raises(auth):
    svc, _ = auth
    svc.register("alice", "x")
    with pytest.raises(UsernameTaken):
        svc.register("alice", "y")


def test_register_translates_repo_duplicate_into_username_taken():
    # Race path: the pre-check passes (get returns None), but the repo's insert
    # loses the race and raises UsernameAlreadyExists (the unique index firing).
    # The service must map that to the same UsernameTaken the caller expects.
    class RacingRepo(FakeUserRepository):
        def save(self, user: User):
            raise UsernameAlreadyExists(user.username)

    svc = AuthService(
        user_repository=RacingRepo(),
        refresh_token_repository=FakeRefreshTokenRepository(),
    )
    with pytest.raises(UsernameTaken):
        svc.register("alice", "x")


# --- authentication issues both tokens ---

def test_authenticate_returns_access_and_stored_refresh(auth):
    svc, refresh_repo = auth
    svc.register("alice", "secret123")
    access, refresh = svc.authenticate("alice", "secret123")
    assert security.decode_access_token(access) == "alice"
    username, jti = security.decode_refresh_token(refresh)
    assert username == "alice"
    assert refresh_repo.exists(jti)  # allowlisted on login


def test_authenticate_wrong_password_raises(auth):
    svc, _ = auth
    svc.register("alice", "secret123")
    with pytest.raises(InvalidCredentials):
        svc.authenticate("alice", "wrong")


def test_authenticate_unknown_user_raises_same_error(auth):
    # Enumeration defense: unknown user and wrong password are indistinguishable.
    svc, _ = auth
    with pytest.raises(InvalidCredentials):
        svc.authenticate("nobody", "whatever")


# --- refresh ---

def test_refresh_returns_a_new_access_token(auth):
    svc, _ = auth
    svc.register("alice", "secret123")
    _, refresh = svc.authenticate("alice", "secret123")
    access = svc.refresh(refresh)
    assert security.decode_access_token(access) == "alice"


def test_refresh_after_logout_is_rejected(auth):
    svc, _ = auth
    svc.register("alice", "secret123")
    _, refresh = svc.authenticate("alice", "secret123")
    svc.logout(refresh)
    with pytest.raises(InvalidRefreshToken):
        svc.refresh(refresh)


def test_refresh_with_garbage_is_rejected(auth):
    svc, _ = auth
    with pytest.raises(InvalidRefreshToken):
        svc.refresh("not.a.jwt")


def test_refresh_with_an_access_token_is_rejected(auth):
    # cross-type: an access token must not be exchangeable for a new one
    svc, _ = auth
    svc.register("alice", "secret123")
    access, _ = svc.authenticate("alice", "secret123")
    with pytest.raises(InvalidRefreshToken):
        svc.refresh(access)


# --- logout revokes ---

def test_logout_removes_the_jti_from_the_allowlist(auth):
    svc, refresh_repo = auth
    svc.register("alice", "secret123")
    _, refresh = svc.authenticate("alice", "secret123")
    _, jti = security.decode_refresh_token(refresh)
    assert refresh_repo.exists(jti)
    svc.logout(refresh)
    assert not refresh_repo.exists(jti)


def test_logout_with_garbage_is_a_noop(auth):
    svc, _ = auth
    svc.logout("not.a.jwt")  # must not raise
