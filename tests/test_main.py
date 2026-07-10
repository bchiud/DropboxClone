"""App lifespan test.

Entering the TestClient context manager triggers startup (the Notifier's
background subscribe-loop) and exiting triggers shutdown (task cancel). With
redis_url unset, the bus is in-memory, so this needs no Redis.
"""
from fastapi.testclient import TestClient

from app.main import app


def test_lifespan_starts_and_stops_cleanly():
    with TestClient(app) as client:  # runs startup + shutdown
        assert client.get("/docs").status_code == 200
