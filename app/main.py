from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import Response

from app.dependencies import get_file_service
from app.domain.services import FileService

app = FastAPI(title="Dropbox Clone")
CURRENT_OWNER = "test-user"  # temp placeholder user


@app.post("/files")
async def upload(
        path: str, file: UploadFile = File(...),
        service: FileService = Depends(get_file_service),
) -> dict:
    data = await file.read()
    doc: dict = service.save_file(CURRENT_OWNER, path, data)
    return {
        "path": doc["path"],
        "size": doc["size"],
        "blocks": len(doc["block_hashes"]),
    }


@app.get("/files")
def list_files(
        service: FileService = Depends(get_file_service),
) -> dict:
    return {"files": service.list_files(CURRENT_OWNER)}


@app.get("/files/content")
def download(
        path: str,
        service: FileService = Depends(get_file_service),
):
    try:
        data = service.load_file(CURRENT_OWNER, path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="file not found")
    return Response(content=data, media_type="application/octet-stream")
