from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

Handler = Callable[[str], Awaitable[None]]

class ChangeBus(ABC):
    @abstractmethod
    async def publish(self, username: str): ...

    @abstractmethod
    async def listen(self, handler: Handler): ...