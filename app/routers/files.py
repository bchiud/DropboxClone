from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile

from app.application.file_service import FileService
from app.auth_dependencies import get_current_user
from app.dependencies import get_file_service
from app.models.file import FileRecord

router = APIRouter(
    prefix="/files",
    tags=["files"],
)


@router.post("")
async def upload(
        path: str, file: UploadFile = File(...),
        fileService: FileService = Depends(get_file_service),
        current_user: str = Depends(get_current_user),
) -> dict:
    data = await file.read()
    record: FileRecord = fileService.save_file(current_user, path, data)
    return {
        "path": record.path,
        "size": record.size,
        "blocks": len(record.block_hashes),
    }


@router.get("")
def list_files(
        fileService: FileService = Depends(get_file_service),
        current_user: str = Depends(get_current_user),
) -> dict:
    return {"files": fileService.list_files(current_user)}


@router.get("/content")
def download(
        path: str,
        fileService: FileService = Depends(get_file_service),
        current_user: str = Depends(get_current_user),
):
    try:
        data = fileService.load_file(current_user, path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="file not found")
    return Response(content=data, media_type="application/octet-stream")
