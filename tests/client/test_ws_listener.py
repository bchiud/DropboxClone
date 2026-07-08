"""Unit tests for the client WebSocket listener's per-connection handler."""
import asyncio
from unittest.mock import MagicMock

from client.ws_listener import handle_connection


class FakeWs:
    """An async-iterable stand-in for a websocket connection."""

    def __init__(self, messages):
        self._messages = messages

    def __aiter__(self):
        async def gen():
            for m in self._messages:
                yield m
        return gen()


def test_pulls_on_connect_then_per_message():
    engine = MagicMock()
    asyncio.run(handle_connection(FakeWs(["changed", "changed"]), engine))
    assert engine.pull.call_count == 3  # 1 on connect + 2 messages


def test_pulls_once_on_connect_with_no_messages():
    engine = MagicMock()
    asyncio.run(handle_connection(FakeWs([]), engine))
    assert engine.pull.call_count == 1  # catch-up pull even before any nudge
