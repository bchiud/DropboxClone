import asyncio

import websockets

from client.sync import SyncEngine

RECONNECT_SECONDS = 3


async def handle_connection(ws, engine: SyncEngine) -> None:
    engine.pull()  # pull on connect to reconcile changes during (reconnect) gap
    async for _message in ws:
        engine.pull()


async def listen(
        server_url: str,
        token: str,
        engine: SyncEngine,
        reconnect_seconds: float = RECONNECT_SECONDS,
) -> None:  # pragma: no cover  (network reconnect loop — exercised live, not in unit tests)
    ws_url = server_url.replace("http://", "ws://").replace("https://", "wss://")
    url = f"{ws_url}/ws?token={token}"
    while True:
        try:
            async with websockets.connect(url) as websocket:
                await handle_connection(websocket, engine)
        except Exception:
            await asyncio.sleep(reconnect_seconds)
