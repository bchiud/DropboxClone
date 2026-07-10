from app.ports.change_bus import ChangeBus, Handler


class InMemoryChangeBus(ChangeBus):
    def __init__(self) -> None:
        self._handler: Handler | None = None

    async def listen(self, handler: Handler) -> None:
        self._handler = handler

    async def publish(self, username: str) -> None:
        if self._handler is not None:
            await self._handler(username)
