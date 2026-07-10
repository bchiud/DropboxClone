"""Unit tests for the in-memory ChangeBus (single-process, zero-Redis default)."""
import asyncio

import pytest

from app.adapters.in_memory_change_bus import InMemoryChangeBus
from app.ports.change_bus import ChangeBus


def test_is_a_change_bus():
    assert isinstance(InMemoryChangeBus(), ChangeBus)


def test_publish_delivers_inline_to_the_registered_handler():
    bus = InMemoryChangeBus()
    seen: list[str] = []

    async def handler(username: str) -> None:
        seen.append(username)

    async def scenario() -> None:
        await bus.listen(handler)
        await bus.publish("alice")

    asyncio.run(scenario())
    assert seen == ["alice"]


def test_publish_before_listen_is_a_noop():
    # no handler registered yet -> nothing to deliver to, must not raise
    bus = InMemoryChangeBus()
    asyncio.run(bus.publish("alice"))
