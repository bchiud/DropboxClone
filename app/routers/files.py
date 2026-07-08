from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status

from app.application.file_service import FileService, MissingBlocks
from app.auth_dependencies import get_current_user
from app.dependencies import get_file_service
from app.models.file import CommitFileRequest, FileRecord

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


# --- Server Upload Endpoints ---

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


# --- Client Upload Endpoints ---

@router.post("/commit", status_code=status.HTTP_201_CREATED)
def commit(
        body: CommitFileRequest,
        fileService: FileService = Depends(get_file_service),
        current_user: str = Depends(get_current_user),
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
