from fastapi import APIRouter, Depends

from app.application.share_service import ShareService
from app.auth_dependencies import get_current_user
from app.dependencies import get_share_service
from app.models.share import Share, ShareLink, ShareLinkRequest, ShareRequest

router = APIRouter(
    prefix="/shares",
    tags=["shares"],
)


# --- user-to-user sharing ---

@router.post("", response_model=Share)
async def create_share(
        share_request: ShareRequest,
        share_service: ShareService = Depends(get_share_service),
        current_user: str = Depends(get_current_user),
):
    return share_service.share(owner=current_user, path=share_request.path, shared_with=share_request.shared_with)


@router.delete("", status_code=204)
async def delete_share(
        share_request: ShareRequest,
        share_service: ShareService = Depends(get_share_service),
        current_user: str = Depends(get_current_user),
):
    return share_service.revoke(owner=current_user, path=share_request.path, shared_with=share_request.shared_with)


@router.get("/incoming", response_model=list[Share])
async def list_incoming(
        share_service: ShareService = Depends(get_share_service),
        current_user: str = Depends(get_current_user),
):
    return share_service.list_incoming(username=current_user)


@router.get("/outgoing", response_model=list[Share])
async def list_outgoing(
        share_service: ShareService = Depends(get_share_service),
        current_user: str = Depends(get_current_user),
):
    return share_service.list_outgoing(owner=current_user)


### --- public link sharing ---

@router.post("/link")
async def create_share_link(
        share_link_request: ShareLinkRequest,
        share_service: ShareService = Depends(get_share_service),
        current_user: str = Depends(get_current_user),
):
    token = share_service.create_link(owner=current_user, path=share_link_request.path)
    return {"token": token}


@router.delete("/link/{jti}", status_code=204)
async def revoke_share_link(
        jti: str,
        share_service: ShareService = Depends(get_share_service),
        current_user: str = Depends(get_current_user),
):
    share_service.revoke_link(owner=current_user, jti=jti)


@router.get("/link", response_model=list[ShareLink])
async def list_share_links(
        share_service: ShareService = Depends(get_share_service),
        current_user: str = Depends(get_current_user),
) -> list[ShareLink]:
    return share_service.list_links(owner=current_user)
