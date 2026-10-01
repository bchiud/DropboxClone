import asyncio

import websockets
from websockets.exceptions import InvalidStatus

from client.api_client import ApiClient
from client.sync import SyncEngine

RECONNECT_SECONDS = 3


async def handle_connection(ws, engine: SyncEngine) -> None:
    engine.pull()  # pull on connect to reconcile changes during (reconnect) gap
    async for _message in ws:
        engine.pull()


def ws_url(server_url: str, token: str) -> str:
    # websockets can't carry auth headers, so the token rides in the query string
    base = server_url.replace("http://", "ws://").replace("https://", "wss://")
    return f"{base}/ws?token={token}"


def is_auth_rejection(exc: Exception) -> bool:
    # the server rejects a bad or expired token by closing before accept, which the handshake sees as a 403
    return isinstance(exc, InvalidStatus) and exc.response.status_code in (401, 403)


async def listen(
        server_url: str,
        api: ApiClient,
        engine: SyncEngine,
        reconnect_seconds: float = RECONNECT_SECONDS,
) -> None:  # pragma: no cover  (network reconnect loop — exercised live, not in unit tests)
    while True:
        try:
            # read the token on every attempt: the HTTP side may have refreshed it since the last connect
            async with websockets.connect(ws_url(server_url, api.token)) as websocket:
                await handle_connection(websocket, engine)
        except Exception as exc:
            if is_auth_rejection(exc):
                # the access token expired while we were disconnected. refresh() raises if the refresh token
                # has expired too, which ends the client: it needs a fresh login
                api.refresh()
            await asyncio.sleep(reconnect_seconds)
