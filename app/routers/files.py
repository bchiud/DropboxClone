from fastapi import APIRouter, Depends, HTTPException, status

from app.application.file_service import FileService, MissingBlocks
from app.auth_dependencies import get_current_user
from app.dependencies import get_connection_manager, get_file_service
from app.models.file import CommitFileRequest, FileRecord
from app.realtime import ConnectionManager

router = APIRouter(
    prefix="/files",
    tags=["files"],
)


@router.get("")
def list_files(
        fileService: FileService = Depends(get_file_service),
        current_user: str = Depends(get_current_user),
) -> dict:
    return {"files": fileService.list_files(current_user)}


@router.post("/commit", status_code=status.HTTP_201_CREATED)
async def commit(
        body: CommitFileRequest,
        fileService: FileService = Depends(get_file_service),
        current_user: str = Depends(get_current_user),
        connectionManager: ConnectionManager = Depends(get_connection_manager),
) -> dict:
    try:
        fileRecord: FileRecord = fileService.commit_file(
            owner=current_user,
            path=body.path,
            size=body.size,
            block_hashes=body.block_hashes,
        )
    except MissingBlocks as mb:
        raise HTTPException(status_code=409, detail={"missing": mb.hashes})
    
    await connectionManager.notify(current_user)
    return {
        "path": fileRecord.path,
        "size": fileRecord.size,
        "blocks": len(fileRecord.block_hashes),
    }


@router.get("/recipe")
def recipe(
        path: str,
        fileService: FileService = Depends(get_file_service),
        current_user: str = Depends(get_current_user),
) -> dict:
    try:
        fileRecord: FileRecord = fileService.get_recipe(owner=current_user, path=path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="file not found")
    return {
        "path": fileRecord.path,
        "size": fileRecord.size,
        "block_hashes": fileRecord.block_hashes,
    }
