from fastapi import FastAPI

from app.routers import auth, blocks, files

app = FastAPI(title="Dropbox Clone")
app.include_router(auth.router)
app.include_router(blocks.router)
app.include_router(files.router)
