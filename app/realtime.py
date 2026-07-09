from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)

    def add(self, username: str, websocket: WebSocket) -> None:
        self._connections[username].add(websocket)

    def remove(self, username: str, websocket: WebSocket) -> None:
        # set.remove() raises KeyError if key DNE
        self._connections[username].discard(websocket)
        if not self._connections[username]:
            self._connections.pop(username, None)

    async def notify(self, username: str) -> None:
        for websocket in list(self._connections.get(username, set())):
            try:
                await websocket.send_json({"type": "changed"})
            except Exception:
                # prune dead connections
                self.remove(username, websocket)

    def connection_for(self, username: str) -> set[WebSocket]:
        return self._connections.get(username, set())
