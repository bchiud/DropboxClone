from fastapi import FastAPI

from app.routers import auth, blocks, files, link, shares, ws

app = FastAPI(title="Dropbox Clone")
app.include_router(auth.router)
app.include_router(blocks.router)
app.include_router(files.router)
app.include_router(link.router)
app.include_router(shares.router)
app.include_router(ws.router)
