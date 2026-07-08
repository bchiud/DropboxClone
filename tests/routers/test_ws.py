"""Tests for the /ws WebSocket endpoint (auth + registration lifecycle)."""
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.dependencies import get_connection_manager
from app.domain import security
from app.main import app
from app.realtime import ConnectionManager


@pytest.fixture
def setup():
    manager = ConnectionManager()
    app.dependency_overrides[get_connection_manager] = lambda: manager
    yield TestClient(app), manager
    app.dependency_overrides.clear()


def test_valid_token_connects_registers_and_unregisters(setup):
    client, manager = setup
    token = security.create_access_token("alice")
    with client.websocket_connect(f"/ws?token={token}"):
        assert len(manager.connection_for("alice")) == 1
    assert len(manager.connection_for("alice")) == 0  # removed on disconnect


def test_invalid_token_is_rejected(setup):
    client, manager = setup
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws?token=not-a-real-token"):
            pass
    assert exc.value.code == 1008  # policy violation
    assert manager.connection_for("alice") == set()  # never registered
