from fastapi import APIRouter, Depends, HTTPException

from app.application.file_service import BlockNotInFile, FileService
from app.application.share_service import ShareService
from app.dependencies import get_file_service, get_share_service
from app.models.file import BlockHashesRequest, FileRecord

router = APIRouter(prefix="/link", tags=["link"])


def _resolve_share_token(token: str, share_service: ShareService) -> tuple[str, str]:
    resolved: tuple[str, str] | None = share_service.resolve_link(token)
    if resolved is None:
        raise HTTPException(status_code=404, detail="Not found")
    return resolved


@router.get("/recipe")
def link_recipe(
        token: str,
        file_service: FileService = Depends(get_file_service),
        share_service: ShareService = Depends(get_share_service),
) -> dict:
    owner, path = _resolve_share_token(token, share_service)
    try:
        file_record: FileRecord = file_service.get_recipe(owner=owner, path=path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    return {
        "path": file_record.path,
        "size": file_record.size,
        "block_hashes": file_record.block_hashes,
    }


@router.post("/download-urls")
def link_download_urls(
        token: str,
        body: BlockHashesRequest,
        file_service: FileService = Depends(get_file_service),
        share_service: ShareService = Depends(get_share_service),
) -> dict:
    owner, path = _resolve_share_token(token, share_service)
    try:
        hashes_to_urls: dict[str, str] = file_service.download_urls(owner=owner, path=path, hashes=body.hashes)
    except (BlockNotInFile, FileNotFoundError):
        raise HTTPException(status_code=404, detail="File not found")
    return {"urls": hashes_to_urls}
