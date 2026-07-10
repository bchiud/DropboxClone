"""Unit tests for the Redis ChangeBus adapter.

The async redis client is faked (patched at the module's `from_url`), so these
run with no live Redis — they pin the channel name and the message-frame
filtering. Real cross-process delivery is covered by the live smoke test.
"""
import asyncio

import pytest

from app.ports.change_bus import ChangeBus


class FakePubSub:
    def __init__(self, messages):
        self._messages = messages
        self.subscribed = []

    async def subscribe(self, channel):
        self.subscribed.append(channel)

    async def listen(self):
        for m in self._messages:
            yield m


class FakeRedis:
    def __init__(self, messages):
        self.published = []
        self._pubsub = FakePubSub(messages)

    async def publish(self, channel, data):
        self.published.append((channel, data))

    def pubsub(self):
        return self._pubsub


def _bus(monkeypatch, messages):
    from app.adapters.redis_change_bus import RedisChangeBus

    fake = FakeRedis(messages)
    monkeypatch.setattr(
        "app.adapters.redis_change_bus.from_url", lambda *a, **k: fake
    )
    return RedisChangeBus("redis://fake"), fake


def test_is_a_change_bus(monkeypatch):
    bus, _ = _bus(monkeypatch, [])
    assert isinstance(bus, ChangeBus)


def test_publish_sends_username_on_the_changes_channel(monkeypatch):
    bus, fake = _bus(monkeypatch, [])
    asyncio.run(bus.publish("alice"))
    assert fake.published == [("changes", "alice")]


def test_listen_delivers_only_message_frames_to_the_handler(monkeypatch):
    frames = [
        {"type": "subscribe", "data": 1},       # control frame -> ignored
        {"type": "message", "data": "alice"},   # real payload -> delivered
        {"type": "message", "data": "bob"},
    ]
    bus, fake = _bus(monkeypatch, frames)
    seen: list[str] = []

    async def handler(username: str) -> None:
        seen.append(username)

    asyncio.run(bus.listen(handler))
    assert seen == ["alice", "bob"]
    assert fake._pubsub.subscribed == ["changes"]  # subscribed to the right channel
