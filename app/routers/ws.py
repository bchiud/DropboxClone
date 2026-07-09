from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.dependencies import get_connection_manager
from app.domain import security
from app.realtime import ConnectionManager

router = APIRouter(
    prefix="/ws",
    tags=["ws"],
)


@router.websocket("")
async def websocket_endpoint(
        websocket: WebSocket,
        token: str,
        connection_manager: ConnectionManager = Depends(get_connection_manager),
):
    # websockets can't carry auth headers, so token is passed in url query string
    username: str = security.decode_access_token(token)
    if username is None:
        await websocket.close(code=1008)  # policy violation — reject
        return

    await websocket.accept()
    connection_manager.add(username, websocket)
    try:
        while True:
            # client mostly listens, but awaiting receive is how we detect WebSocketDisconnect
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        connection_manager.remove(username, websocket)