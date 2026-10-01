"""HTTP client for the Dropbox-clone server API.

A thin, typed wrapper over the REST endpoints. Holds the auth tokens and
attaches the access token to every protected request — the client-side mirror
of the server's get_current_user. Access tokens expire after 60 minutes, so a
protected call that gets a 401 trades the refresh token for a new access token
and retries once; a long-running sync client keeps working without the password.
"""
import httpx


class PreconditionFailed(Exception):
    """Commit rejected: the file moved since we last synced it (HTTP 412)."""


class ApiClient:
    def __init__(self, base_url: str, token: str | None = None, transport=None):
        # transport is an injection seam for tests (httpx.MockTransport).
        self._http = httpx.Client(base_url=base_url, timeout=30, transport=transport)
        self._token = token
        self._refresh_token: str | None = None

    # --- auth ---

    def register(self, username: str, password: str) -> dict:
        resp = self._http.post(
            "/auth/register",
            json={"username": username, "password": password},
        )
        resp.raise_for_status()
        return resp.json()

    def login(self, username: str, password: str) -> str:
        # OAuth2 password flow expects form-encoded fields, not JSON.
        resp = self._http.post(
            "/auth/login",
            data={"username": username, "password": password},
        )
        resp.raise_for_status()
        body = resp.json()
        self._token = body["access_token"]
        self._refresh_token = body.get("refresh_token")
        return self._token

    def refresh(self) -> str:
        """Trade the refresh token for a new access token. Raises if it's expired or revoked (log in again)."""
        resp = self._http.post("/auth/refresh", json={"refresh_token": self._refresh_token})
        resp.raise_for_status()
        self._token = resp.json()["access_token"]
        return self._token

    @property
    def token(self) -> str | None:
        """The current access token, e.g. for the WebSocket URL (refresh() may have replaced it)."""
        return self._token

    def _auth(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"}

    def _authed(self, method: str, url: str, headers: dict | None = None, **kwargs) -> httpx.Response:
        # every protected call goes through here. A 401 most likely means the access token expired,
        # so refresh it and retry once; a second 401 is returned as-is for the caller to raise.
        def send() -> httpx.Response:
            return self._http.request(method, url, headers={**self._auth(), **(headers or {})}, **kwargs)

        resp = send()
        if resp.status_code == 401 and self._refresh_token is not None:
            self.refresh()
            resp = send()
        return resp

    # --- files ---

    def list_files(self) -> list[dict]:
        resp = self._authed("GET", "/files")
        resp.raise_for_status()
        return resp.json()["files"]

    def close(self) -> None:
        self._http.close()

    # --- blocks: negotiation ---

    def missing_blocks(self, hashes: list[str]) -> list[str]:
        resp = self._authed("POST", "/blocks/missing", json={"hashes": hashes})
        resp.raise_for_status()
        return resp.json()["missing"]

    def upload_urls(self, hashes: list[str]) -> dict[str, str]:
        resp = self._authed("POST", "/blocks/upload-urls", json={"hashes": hashes})
        resp.raise_for_status()
        return resp.json()["urls"]

    def download_urls(self, path: str, hashes: list[str]) -> dict[str, str]:
        resp = self._authed("POST", "/blocks/download-urls", params={"path": path}, json={"hashes": hashes})
        resp.raise_for_status()
        return resp.json()["urls"]

    def commit_file(self, path: str, size: int, block_hashes: list[str], base_etag: str | None) -> str:
        precondition = ({"If-None-Match": "*"} if base_etag is None else {"If-Match": f'"{base_etag}"'})
        resp = self._authed(
            "POST",
            "/files/commit",
            json={"path": path, "size": size, "block_hashes": block_hashes},
            headers=precondition,
        )
        if resp.status_code == 412:
            raise PreconditionFailed(path)
        resp.raise_for_status()
        return resp.headers["ETag"].strip('"')

    def delete_file(self, path: str) -> None:
        resp = self._authed("DELETE", "/files", params={"path": path})
        if resp.status_code == 404:
            return  # already gone (another device deleted it first): the goal is met, so a retry stays safe
        resp.raise_for_status()

    def get_recipe(self, path: str) -> tuple[dict, str]:
        resp = self._authed("GET", "/files/recipe", params={"path": path})
        resp.raise_for_status()
        return resp.json(), resp.headers["ETag"].strip('"')

    # --- block xfer (presigned B2 URLs: they carry their own auth, so no bearer token) ---

    def put_block(self, url: str, data: bytes) -> None:
        resp = self._http.put(url, content=data)
        resp.raise_for_status()

    def get_block(self, url: str) -> bytes:
        resp = self._http.get(url)
        resp.raise_for_status()
        return resp.content
