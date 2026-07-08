"""Unit tests for the ApiClient delta-flow methods (MockTransport, no network)."""
import json

import httpx

from client.api_client import ApiClient


def make_client(handler) -> ApiClient:
    c = ApiClient("http://test", transport=httpx.MockTransport(handler))
    c._token = "tok"
    return c


def test_missing_blocks_posts_json_body():
    def handler(req):
        assert req.url.path == "/blocks/missing"
        assert json.loads(req.content) == {"hashes": ["a", "b"]}   # body, not query
        assert req.headers["Authorization"] == "Bearer tok"
        return httpx.Response(200, json={"missing": ["b"]})
    assert make_client(handler).missing_blocks(["a", "b"]) == ["b"]


def test_upload_urls_unwraps_urls():
    def handler(req):
        assert json.loads(req.content) == {"hashes": ["h1"]}
        return httpx.Response(200, json={"urls": {"h1": "https://b2/put/h1"}})
    assert make_client(handler).upload_urls(["h1"]) == {"h1": "https://b2/put/h1"}


def test_download_urls_unwraps_urls():
    def handler(req):
        return httpx.Response(200, json={"urls": {"h1": "https://b2/get/h1"}})
    assert make_client(handler).download_urls(["h1"]) == {"h1": "https://b2/get/h1"}


def test_commit_file_posts_recipe_body():
    def handler(req):
        assert req.url.path == "/files/commit"
        assert json.loads(req.content) == {"path": "/a.txt", "size": 5, "block_hashes": ["h1"]}
        return httpx.Response(201, json={"path": "/a.txt", "size": 5, "blocks": 1})
    assert make_client(handler).commit_file("/a.txt", 5, ["h1"])["blocks"] == 1


def test_get_recipe_uses_query_param():
    def handler(req):
        assert req.url.path == "/files/recipe"
        assert req.url.params["path"] == "/a.txt"
        return httpx.Response(200, json={"path": "/a.txt", "size": 5, "block_hashes": ["h1"]})
    assert make_client(handler).get_recipe("/a.txt")["block_hashes"] == ["h1"]


def test_put_block_sends_bytes_without_auth_header():
    def handler(req):
        assert req.method == "PUT"
        assert "Authorization" not in req.headers   # presigned URL carries its own auth
        assert req.content == b"blockdata"
        return httpx.Response(200)
    make_client(handler).put_block("https://b2/presigned-put", b"blockdata")


def test_get_block_returns_bytes_without_auth_header():
    def handler(req):
        assert req.method == "GET"
        assert "Authorization" not in req.headers
        return httpx.Response(200, content=b"blockdata")
    assert make_client(handler).get_block("https://b2/presigned-get") == b"blockdata"
