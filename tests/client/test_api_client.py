"""Unit tests for the sync client's ApiClient.

Uses httpx.MockTransport to stub the server — no network, no running app.
"""
import json

import httpx
import pytest

from client.api_client import ApiClient


def make_client(handler) -> ApiClient:
    return ApiClient("http://test", transport=httpx.MockTransport(handler))


def test_register_posts_json():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/auth/register"
        assert json.loads(request.content) == {"username": "alice", "password": "pw"}
        return httpx.Response(201, json={"username": "alice", "created_at": "t"})

    client = make_client(handler)
    assert client.register("alice", "pw")["username"] == "alice"


def test_login_posts_form_and_stores_token():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/auth/login"
        assert b"username=alice" in request.content  # form-encoded, not JSON
        return httpx.Response(200, json={"access_token": "tok123", "token_type": "bearer"})

    client = make_client(handler)
    assert client.login("alice", "pw") == "tok123"
    assert client._token == "tok123"


def test_list_files_sends_bearer_token():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer tok123"
        return httpx.Response(200, json={"files": [{"path": "/a.txt"}]})

    client = make_client(handler)
    client._token = "tok123"
    assert client.list_files() == [{"path": "/a.txt"}]


def test_upload_sends_file_and_path():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/files"
        assert request.url.params["path"] == "/a.txt"
        assert b"hello" in request.content
        return httpx.Response(200, json={"path": "/a.txt", "size": 5, "blocks": 1})

    client = make_client(handler)
    client._token = "tok123"
    assert client.upload("/a.txt", b"hello")["size"] == 5


def test_download_returns_bytes():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/files/content"
        assert request.url.params["path"] == "/a.txt"
        return httpx.Response(200, content=b"file bytes")

    client = make_client(handler)
    client._token = "tok123"
    assert client.download("/a.txt") == b"file bytes"


def test_raise_for_status_propagates_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "unauthorized"})

    client = make_client(handler)
    client._token = "bad"
    with pytest.raises(httpx.HTTPStatusError):
        client.list_files()


def test_close_is_callable():
    client = make_client(lambda r: httpx.Response(200))
    client.close()
