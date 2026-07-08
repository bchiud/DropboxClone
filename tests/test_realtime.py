"""Unit tests for the WebSocket ConnectionManager."""
import asyncio
from unittest.mock import AsyncMock

from app.realtime import ConnectionManager


def test_add_registers_connection():
    m = ConnectionManager()
    ws = AsyncMock()
    m.add("alice", ws)
    assert ws in m.connection_for("alice")


def test_multiple_devices_per_user():
    m = ConnectionManager()
    a1, a2 = AsyncMock(), AsyncMock()
    m.add("alice", a1)
    m.add("alice", a2)
    assert len(m.connection_for("alice")) == 2


def test_remove_drops_connection_and_cleans_key():
    m = ConnectionManager()
    ws = AsyncMock()
    m.add("u", ws)
    m.remove("u", ws)
    assert m.connection_for("u") == set()


def test_remove_absent_is_safe():
    m = ConnectionManager()
    m.remove("nobody", AsyncMock())  # must not raise


def test_notify_fans_out_to_all_user_devices_only():
    m = ConnectionManager()
    a1, a2, b1 = AsyncMock(), AsyncMock(), AsyncMock()
    m.add("alice", a1)
    m.add("alice", a2)
    m.add("bob", b1)

    asyncio.run(m.notify("alice"))

    a1.send_json.assert_awaited_once_with({"type": "changed"})
    a2.send_json.assert_awaited_once_with({"type": "changed"})
    b1.send_json.assert_not_awaited()


def test_notify_unknown_user_is_noop():
    m = ConnectionManager()
    asyncio.run(m.notify("ghost"))  # must not raise


def test_notify_prunes_dead_connections():
    m = ConnectionManager()
    dead = AsyncMock()
    dead.send_json.side_effect = RuntimeError("socket closed")
    m.add("u", dead)

    asyncio.run(m.notify("u"))

    assert m.connection_for("u") == set()  # pruned after send failed
