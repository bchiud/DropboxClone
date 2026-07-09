from fastapi import APIRouter, Depends, HTTPException

from app.application.file_service import FileService
from app.dependencies import get_file_service
from app.domain.security import decode_share_token
from app.models.file import BlockHashesRequest, FileRecord

router = APIRouter(prefix="/link", tags=["link"])


def _decode_share_token(token: str) -> tuple[str, str]:
    decoded: tuple[str, str] | None = decode_share_token(token)
    if decoded is None:
        raise HTTPException(status_code=404, detail="Not found")
    return decoded


@router.get("/recipe")
def link_recipe(
        token: str,
        fileService: FileService = Depends(get_file_service),
) -> dict:
    owner, path = _decode_share_token(token)
    try:
        fileRecord: FileRecord = fileService.get_recipe(owner=owner, path=path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    return {
        "path": fileRecord.path,
        "size": fileRecord.size,
        "block_hashes": fileRecord.block_hashes,
    }


@router.post("/download-urls")
def link_download_urls(
        token: str,
        body: BlockHashesRequest,
        fileService: FileService = Depends(get_file_service),
) -> dict:
    owner, _path = _decode_share_token(token)
    return {"urls": fileService.download_urls(owner=owner, hashes=body.hashes)}
