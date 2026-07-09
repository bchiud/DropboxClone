from fastapi import APIRouter, Depends, HTTPException, status

from app.application.file_service import FileService, MissingBlocks
from app.application.share_service import ShareService
from app.auth_dependencies import get_current_user
from app.dependencies import get_connection_manager, get_file_service, get_share_service
from app.models.file import CommitFileRequest, FileRecord
from app.realtime import ConnectionManager

router = APIRouter(
    prefix="/files",
    tags=["files"],
)


@router.get("")
def list_files(
        file_service: FileService = Depends(get_file_service),
        current_user: str = Depends(get_current_user),
) -> dict:
    return {"files": file_service.list_files(current_user)}


@router.post("/commit", status_code=status.HTTP_201_CREATED)
async def commit(
        body: CommitFileRequest,
        file_service: FileService = Depends(get_file_service),
        current_user: str = Depends(get_current_user),
        connection_manager: ConnectionManager = Depends(get_connection_manager),
) -> dict:
    try:
        file_record: FileRecord = file_service.commit_file(
            owner=current_user,
            path=body.path,
            size=body.size,
            block_hashes=body.block_hashes,
        )
    except MissingBlocks as mb:
        raise HTTPException(status_code=409, detail={"missing": mb.hashes})

    await connection_manager.notify(current_user)
    return {
        "path": file_record.path,
        "size": file_record.size,
        "blocks": len(file_record.block_hashes),
    }


@router.get("/recipe")
def recipe(
        path: str,
        owner: str | None = None,
        file_service: FileService = Depends(get_file_service),
        share_service: ShareService = Depends(get_share_service),
        current_user: str = Depends(get_current_user),
) -> dict:
    owner = owner or current_user
    if not share_service.can_read(requester=current_user, path=path, owner=owner):
        raise HTTPException(status_code=404, detail="File not found")
    try:
        file_record: FileRecord = file_service.get_recipe(owner=owner, path=path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    return {
        "path": file_record.path,
        "size": file_record.size,
        "block_hashes": file_record.block_hashes,
    }
