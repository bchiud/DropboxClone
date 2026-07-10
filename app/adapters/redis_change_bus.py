from redis.asyncio import from_url

from app.ports.change_bus import ChangeBus, Handler

CHANNEL = "changes"


class RedisChangeBus(ChangeBus):
    def __init__(self, url: str) -> None:
        # decode_responses=True -> response arrives as str, not bytes
        self._redis = from_url(url, decode_responses=True)

    async def publish(self, username: str) -> None:
        await self._redis.publish(CHANNEL, username)

    async def listen(self, handler: Handler) -> None:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(CHANNEL)
        async for message in pubsub.listen():
            if message["type"] == "message":
                await handler(message["data"])