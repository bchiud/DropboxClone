from fastapi import APIRouter, Depends, HTTPException

from app.application.file_service import FileService
from app.application.share_service import ShareService
from app.auth_dependencies import get_current_user
from app.dependencies import get_file_service, get_share_service
from app.models.file import BlockHashesRequest

router = APIRouter(prefix="/blocks", tags=["blocks"])


@router.post("/missing")
def missing_blocks(
        body: BlockHashesRequest,
        fileService: FileService = Depends(get_file_service),
        current_user: str = Depends(get_current_user),
) -> dict:
    return {"missing": fileService.missing_blocks(owner=current_user, hashes=body.hashes)}


@router.post("/upload-urls")
def upload_urls(
        body: BlockHashesRequest,
        fileService: FileService = Depends(get_file_service),
        current_user: str = Depends(get_current_user),
) -> dict:
    return {"urls": fileService.upload_urls(owner=current_user, hashes=body.hashes)}


@router.post("/download-urls")
def download_urls(
        body: BlockHashesRequest,
        owner: str | None = None,
        path: str | None = None,
        fileService: FileService = Depends(get_file_service),
        shareService: ShareService = Depends(get_share_service),
        current_user: str = Depends(get_current_user),
) -> dict:
    owner = owner or current_user
    if not shareService.can_read(requester=current_user, path=path, owner=owner):
        raise HTTPException(status_code=404, detail="File not found")
    return {"urls": fileService.download_urls(owner=owner, hashes=body.hashes)}
