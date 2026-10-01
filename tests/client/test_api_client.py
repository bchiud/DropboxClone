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
        return httpx.Response(200, json={"access_token": "tok123", "refresh_token": "ref456",
                                         "token_type": "bearer"})

    client = make_client(handler)
    assert client.login("alice", "pw") == "tok123"
    assert client.token == "tok123"
    assert client._refresh_token == "ref456"  # kept so an expired access token can be renewed


def test_list_files_sends_bearer_token():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer tok123"
        return httpx.Response(200, json={"files": [{"path": "/a.txt"}]})

    client = make_client(handler)
    client._token = "tok123"
    assert client.list_files() == [{"path": "/a.txt"}]


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


# --- access-token refresh (access tokens expire after 60 min; the sync client runs for days) ---

def _expiring_server(seen: list[httpx.Request]):
    """/auth/refresh mints "fresh"; protected routes accept only "fresh" and 401 anything else."""
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/auth/refresh":
            assert json.loads(request.content) == {"refresh_token": "ref"}
            return httpx.Response(200, json={"access_token": "fresh", "token_type": "bearer"})
        if request.headers["Authorization"] != "Bearer fresh":
            return httpx.Response(401, json={"detail": "invalid or expired token"})
        return httpx.Response(200, json={"files": []})
    return handler


def _client_with_expired_token(handler) -> ApiClient:
    client = make_client(handler)
    client._token, client._refresh_token = "expired", "ref"
    return client


def test_a_401_refreshes_the_access_token_and_retries_once():
    seen: list[httpx.Request] = []
    client = _client_with_expired_token(_expiring_server(seen))

    assert client.list_files() == []
    assert [r.url.path for r in seen] == ["/files", "/auth/refresh", "/files"]
    assert seen[-1].headers["Authorization"] == "Bearer fresh"
    assert client.token == "fresh"  # later calls (and the WebSocket reconnect) use the new token


def test_the_retry_after_a_refresh_keeps_the_requests_own_headers():
    # commit's If-Match precondition must survive the retry, or the retry would skip the etag check
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/files/commit" and request.headers["Authorization"] == "Bearer fresh":
            seen.append(request)
            return httpx.Response(200, headers={"ETag": '"e2"'})
        return _expiring_server([])(request)

    assert _client_with_expired_token(handler).commit_file("/a.txt", 1, ["h"], "e1") == "e2"
    assert seen[0].headers["If-Match"] == '"e1"'


def test_a_second_401_after_refreshing_is_raised_not_retried_again():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/auth/refresh":
            return httpx.Response(200, json={"access_token": "still-bad", "token_type": "bearer"})
        return httpx.Response(401, json={"detail": "invalid or expired token"})

    with pytest.raises(httpx.HTTPStatusError):
        _client_with_expired_token(handler).list_files()
    assert [r.url.path for r in seen] == ["/files", "/auth/refresh", "/files"]  # exactly one retry, no loop


def test_an_expired_refresh_token_raises_so_the_user_logs_in_again():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Invalid or expired refresh token"})

    with pytest.raises(httpx.HTTPStatusError):
        _client_with_expired_token(handler).list_files()


def test_without_a_refresh_token_a_401_is_not_retried():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(401, json={"detail": "unauthorized"})

    client = make_client(handler)
    client._token = "bad"  # e.g. constructed with a bare token, never logged in
    with pytest.raises(httpx.HTTPStatusError):
        client.list_files()
    assert len(seen) == 1
