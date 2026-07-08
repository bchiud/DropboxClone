from fastapi import APIRouter, Depends

from app.application.file_service import FileService
from app.auth_dependencies import get_current_user
from app.dependencies import get_file_service
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
        fileService: FileService = Depends(get_file_service),
        current_user: str = Depends(get_current_user),
) -> dict:
    return {"urls": fileService.download_urls(owner=current_user, hashes=body.hashes)}
