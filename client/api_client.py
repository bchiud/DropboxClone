"""HTTP client for the Dropbox-clone server API.

A thin, typed wrapper over the REST endpoints. Holds the auth token and
attaches it to every protected request — the client-side mirror of the
server's get_current_user.
"""
import httpx


class ApiClient:
    def __init__(self, base_url: str, token: str | None = None, transport=None):
        # transport is an injection seam for tests (httpx.MockTransport).
        self._http = httpx.Client(base_url=base_url, timeout=30, transport=transport)
        self._token = token

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
        self._token = resp.json()["access_token"]
        return self._token

    def _auth(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"}

    # --- files ---

    def list_files(self) -> list[dict]:
        resp = self._http.get("/files", headers=self._auth())
        resp.raise_for_status()
        return resp.json()["files"]

    def close(self) -> None:
        self._http.close()

    # --- blocks: negotiation ---

    def missing_blocks(self, hashes: list[str]) -> list[str]:
        resp = self._http.post(
            "/blocks/missing",
            json={"hashes": hashes},
            headers=self._auth(),
        )
        resp.raise_for_status()
        return resp.json()["missing"]

    def upload_urls(self, hashes: list[str]) -> dict[str, str]:
        resp = self._http.post(
            "/blocks/upload-urls",
            json={"hashes": hashes},
            headers=self._auth(),
        )
        resp.raise_for_status()
        return resp.json()["urls"]

    def download_urls(self, hashes: list[str]) -> dict[str, str]:
        resp = self._http.post(
            "/blocks/download-urls",
            json={"hashes": hashes},
            headers=self._auth(),
        )
        resp.raise_for_status()
        return resp.json()["urls"]

    def commit_file(self, path: str, size: int, block_hashes: list[str]) -> dict:
        resp = self._http.post(
            "/files/commit",
            json={"path": path, "size": size, "block_hashes": block_hashes},
            headers=self._auth(),
        )
        resp.raise_for_status()
        return resp.json()

    def get_recipe(self, path: str) -> dict:
        resp = self._http.get(
            "/files/recipe",
            params={"path": path},
            headers=self._auth(),
        )
        resp.raise_for_status()
        return resp.json()

    # --- block xfer ---

    def put_block(self, url: str, data: bytes) -> None:
        resp = self._http.put(url, content=data)
        resp.raise_for_status()

    def get_block(self, url: str) -> bytes:
        resp = self._http.get(url)
        resp.raise_for_status()
        return resp.content
