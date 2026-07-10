from datetime import UTC, datetime, timedelta

from app.config import settings
from app.domain.security import create_share_token, decode_share_token, new_jti
from app.models.share import Share, ShareLink
from app.ports.share_link_repository import ShareLinkRepository
from app.ports.share_repository import ShareRepository


class ShareService:
    def __init__(
            self,
            share_repository: ShareRepository,
            share_link_repository: ShareLinkRepository,
    ) -> None:
        self._share_repository = share_repository
        self._share_link_repository = share_link_repository

    def purge_for_file(self, owner: str, path: str) -> list[str]:
        shared_withs: list[str] = self._share_repository.list_recipients_for_path(owner, path)
        self._share_repository.remove_all_for_path(owner, path)
        self._share_link_repository.delete_all_for_path(owner, path)
        return shared_withs

    # --- user-to-user sharing ---

    def share(self, owner: str, path: str, shared_with: str) -> Share:
        share: Share = Share(owner=owner, path=path, shared_with=shared_with)
        self._share_repository.add(share)
        return share

    def revoke(self, owner: str, path: str, shared_with: str) -> None:
        self._share_repository.remove(owner=owner, path=path, shared_with=shared_with)

    def list_incoming(self, username: str) -> list[Share]:
        return self._share_repository.list_for_recipient(username=username)

    def list_outgoing(self, owner: str) -> list[Share]:
        return self._share_repository.list_for_owner(owner=owner)

    def can_read(self, requester: str, owner: str, path: str) -> bool:
        return requester == owner or self._share_repository.exists(owner=owner, path=path, shared_with=requester)

    # --- public link management ---

    def create_link(self, owner: str, path: str) -> str:
        jti: str = new_jti()
        expires_at: datetime = datetime.now(UTC) + timedelta(minutes=settings.share_link_expire_minutes)
        self._share_link_repository.add(ShareLink(jti=jti, owner=owner, path=path, expires_at=expires_at))
        return create_share_token(owner=owner, path=path, jti=jti, expires_at=expires_at)

    def revoke_link(self, owner: str, jti: str) -> None:
        self._share_link_repository.delete(owner=owner, jti=jti)

    def list_links(self, owner: str) -> list[ShareLink]:
        return self._share_link_repository.list_for_owner(owner=owner)

    def resolve_link(self, token: str) -> tuple[str, str] | None:
        decoded = decode_share_token(token)
        if decoded is None:
            return None
        owner, path, jti = decoded
        if not self._share_link_repository.exists(jti=jti):
            return None
        return owner, path
