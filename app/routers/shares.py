from fastapi import APIRouter, Depends

from app.application.share_service import ShareService
from app.auth_dependencies import get_current_user
from app.dependencies import get_share_service
from app.domain.security import create_share_token
from app.models.share import Share, ShareLinkRequest, ShareRequest

router = APIRouter(
    prefix="/shares",
    tags=["shares"],
)


@router.post("", response_model=Share)
async def create_share(
        shareRequest: ShareRequest,
        shareService: ShareService = Depends(get_share_service),
        current_user: str = Depends(get_current_user),
):
    return shareService.share(owner=current_user, path=shareRequest.path, shared_with=shareRequest.shared_with)


@router.delete("", status_code=204)
async def delete_share(
        shareRequest: ShareRequest,
        shareService: ShareService = Depends(get_share_service),
        current_user: str = Depends(get_current_user),
):
    return shareService.revoke(owner=current_user, path=shareRequest.path, shared_with=shareRequest.shared_with)

@router.get("/incoming", response_model=list[Share])
async def list_incoming(
        shareService: ShareService = Depends(get_share_service),
        current_user: str = Depends(get_current_user),
):
    return shareService.list_incoming(username=current_user)

@router.get("/outgoing", response_model=list[Share])
async def list_outgoing(
        shareService: ShareService = Depends(get_share_service),
        current_user: str = Depends(get_current_user),
):
    return shareService.list_outgoing(owner=current_user)


@router.post("/link")
async def create_share_link(
        shareLinkRequest: ShareLinkRequest,
        current_user: str = Depends(get_current_user),
):
    token = create_share_token(owner=current_user, path=shareLinkRequest.path)
    return {"token": token}