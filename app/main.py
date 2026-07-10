import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.dependencies import get_notifier
from app.routers import auth, blocks, files, link, shares, ws


@asynccontextmanager
async def lifespan(app: FastAPI):
    notifier = get_notifier()
    task = asyncio.create_task(notifier.start())  # background subscribe-loop
    yield
    task.cancel()


app = FastAPI(title="Dropbox Clone", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(blocks.router)
app.include_router(files.router)
app.include_router(link.router)
app.include_router(shares.router)
app.include_router(ws.router)
