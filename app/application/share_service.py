from app.models.share import Share
from app.ports.share_repository import ShareRepository


class ShareService:
    def __init__(self, share_repository: ShareRepository) -> None:
        self._share_repository = share_repository

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
