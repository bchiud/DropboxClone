from fastapi import APIRouter, Depends, HTTPException, Header, Response, status

from app.application.file_service import FileService, MissingBlocks
from app.application.share_service import ShareService
from app.auth_dependencies import get_current_user
from app.dependencies import get_file_service, get_notifier, get_share_service
from app.models.file import CommitFileRequest, FileRecord
from app.models.types import RootedPath
from app.ports.file_repository import VersionConflict
from app.realtime import Notifier

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


@router.post("/commit", status_code=status.HTTP_201_CREATED, responses={200: {"description": "Updated"}})
async def commit(
        body: CommitFileRequest,
        response: Response,
        if_match: str | None = Header(default=None),
        if_none_match: str | None = Header(default=None),
        file_service: FileService = Depends(get_file_service),
        current_user: str = Depends(get_current_user),
        notifier: Notifier = Depends(get_notifier),
) -> dict:
    if if_none_match == "*":
        expected_etag = None  # create
    elif if_match is not None:
        expected_etag = if_match.strip('"')
    else:
        raise HTTPException(428, "Precondition Required")
    try:
        file_record: FileRecord = file_service.commit_file(
            owner=current_user,
            path=body.path,
            size=body.size,
            block_hashes=body.block_hashes,
            expected_etag=expected_etag,
        )
    except MissingBlocks as mb:
        raise HTTPException(status_code=409, detail={"missing": mb.hashes})
    except VersionConflict:
        raise HTTPException(status_code=412, detail="etag mismatch")

    await notifier.notify(current_user)
    if expected_etag is not None:  # update, not a create
        response.status_code = status.HTTP_200_OK
    response.headers["ETag"] = f'"{file_record.etag}"'
    return {
        "path": file_record.path,
        "size": file_record.size,
        "blocks": len(file_record.block_hashes),
    }


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete(
        path: RootedPath,
        file_service: FileService = Depends(get_file_service),
        share_service: ShareService = Depends(get_share_service),
        notifier: Notifier = Depends(get_notifier),
        current_user: str = Depends(get_current_user),
) -> None:
    try:
        shared_withs: list[str] = share_service.purge_for_file(owner=current_user, path=path)
        for shared_with in shared_withs:
            await notifier.notify(shared_with)
        file_service.delete_file(owner=current_user, path=path)
        await notifier.notify(current_user)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")


@router.get("/recipe")
def recipe(
        path: RootedPath,
        response: Response,
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
    response.headers["ETag"] = f'"{file_record.etag}"'
    return {
        "path": file_record.path,
        "size": file_record.size,
        "block_hashes": file_record.block_hashes,
    }
