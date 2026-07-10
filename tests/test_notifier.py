"""Unit tests for Notifier — the ChangeBus <-> ConnectionManager bridge.

Uses the in-memory bus, so publish delivers inline: notify() lands on the
local sockets exactly as a Redis round-trip would on the owning server.
"""
import asyncio
from unittest.mock import AsyncMock

from app.adapters.in_memory_change_bus import InMemoryChangeBus
from app.realtime import ConnectionManager, Notifier


def _wire():
    bus = InMemoryChangeBus()
    manager = ConnectionManager()
    return Notifier(bus, manager), manager


def test_notify_reaches_the_users_local_sockets():
    notifier, manager = _wire()
    ws = AsyncMock()
    manager.add("alice", ws)

    async def scenario():
        await notifier.start()          # register manager.notify as the handler
        await notifier.notify("alice")  # publish -> deliver locally

    asyncio.run(scenario())
    ws.send_json.assert_awaited_once_with({"type": "changed"})


def test_notify_targets_only_the_named_user():
    notifier, manager = _wire()
    alice_ws, bob_ws = AsyncMock(), AsyncMock()
    manager.add("alice", alice_ws)
    manager.add("bob", bob_ws)

    async def scenario():
        await notifier.start()
        await notifier.notify("alice")

    asyncio.run(scenario())
    alice_ws.send_json.assert_awaited_once()
    bob_ws.send_json.assert_not_awaited()


def test_notify_before_start_does_not_crash():
    # no listen() yet -> bus has no handler; publish is a safe no-op
    notifier, manager = _wire()
    manager.add("alice", AsyncMock())
    asyncio.run(notifier.notify("alice"))  # must not raise
