"""Unit tests for the ApiClient delta-flow methods (MockTransport, no network)."""
import json

import httpx
import pytest

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


def test_download_urls_sends_path_as_query_and_unwraps_urls():
    def handler(req):
        # path rides in the query string (server reads it there); only hashes in the body
        assert req.url.params.get("path") == "/a.txt"
        assert json.loads(req.content) == {"hashes": ["h1"]}
        return httpx.Response(200, json={"urls": {"h1": "https://b2/get/h1"}})
    assert make_client(handler).download_urls("/a.txt", ["h1"]) == {"h1": "https://b2/get/h1"}


def test_commit_file_creates_with_if_none_match_and_returns_new_etag():
    def handler(req):
        assert req.url.path == "/files/commit"
        assert json.loads(req.content) == {"path": "/a.txt", "size": 5, "block_hashes": ["h1"]}
        assert req.headers["If-None-Match"] == "*"          # base_etag None -> create
        assert "If-Match" not in req.headers
        return httpx.Response(201, headers={"ETag": '"new-etag"'})
    assert make_client(handler).commit_file("/a.txt", 5, ["h1"], base_etag=None) == "new-etag"


def test_commit_file_updates_with_if_match_header():
    def handler(req):
        assert req.headers["If-Match"] == '"base-etag"'     # base etag -> conditional update
        assert "If-None-Match" not in req.headers
        return httpx.Response(200, headers={"ETag": '"new-etag"'})
    assert make_client(handler).commit_file("/a.txt", 5, ["h1"], base_etag="base-etag") == "new-etag"


def test_commit_file_raises_precondition_failed_on_412():
    from client.api_client import PreconditionFailed
    def handler(req):
        return httpx.Response(412)
    with pytest.raises(PreconditionFailed):
        make_client(handler).commit_file("/a.txt", 5, ["h1"], base_etag="stale")


def test_get_recipe_returns_body_and_etag_from_header():
    def handler(req):
        assert req.url.path == "/files/recipe"
        assert req.url.params["path"] == "/a.txt"
        return httpx.Response(200, headers={"ETag": '"the-etag"'},
                              json={"path": "/a.txt", "size": 5, "block_hashes": ["h1"]})
    recipe, etag = make_client(handler).get_recipe("/a.txt")
    assert recipe["block_hashes"] == ["h1"]
    assert etag == "the-etag"


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


def test_delete_file_sends_path_as_query_with_auth():
    def handler(req):
        assert req.method == "DELETE"
        assert req.url.path == "/files"
        assert req.url.params.get("path") == "/a.txt"
        assert req.headers["Authorization"] == "Bearer tok"
        return httpx.Response(204)
    make_client(handler).delete_file("/a.txt")


def test_delete_file_treats_404_as_already_deleted():
    # another device deleted it first: the delete's goal is met, so it must not fail the sync
    make_client(lambda req: httpx.Response(404, json={"detail": "File not found"})).delete_file("/a.txt")


def test_delete_file_raises_on_other_errors():
    with pytest.raises(httpx.HTTPStatusError):
        make_client(lambda req: httpx.Response(500)).delete_file("/a.txt")
