"""Unit tests for the client WebSocket listener's per-connection handler."""
import asyncio
from unittest.mock import MagicMock

import pytest
from websockets.datastructures import Headers
from websockets.exceptions import InvalidStatus
from websockets.http11 import Response

from client.ws_listener import handle_connection, is_auth_rejection, ws_url


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


# --- reconnecting after the access token expired ---

@pytest.mark.parametrize("server, expected", [
    ("http://127.0.0.1:8000", "ws://127.0.0.1:8000/ws?token=tok"),
    ("https://sync.example.com", "wss://sync.example.com/ws?token=tok"),
])
def test_ws_url_maps_the_scheme_and_carries_the_token(server, expected):
    assert ws_url(server, "tok") == expected


def _rejected(status: int) -> InvalidStatus:
    return InvalidStatus(Response(status, "", Headers()))


@pytest.mark.parametrize("status", [401, 403])
def test_a_rejected_handshake_counts_as_an_auth_failure(status):
    # the server closes before accept on a bad/expired token, which the handshake sees as a 403
    assert is_auth_rejection(_rejected(status))


@pytest.mark.parametrize("exc", [_rejected(500), OSError("connection refused"), ConnectionResetError()])
def test_other_connection_failures_are_not_auth_failures(exc):
    # these just back off and retry; refreshing the token wouldn't help
    assert not is_auth_rejection(exc)
