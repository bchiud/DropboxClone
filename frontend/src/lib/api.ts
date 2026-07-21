// --- client state ---
// access token: in memory (short-lived; re-minted from the refresh token as needed)
// refresh token: localStorage, so the session survives a page reload
let token: string | null = null;
const REFRESH_KEY = "refresh_token";

export function setToken(t: string | null) {
  token = t;
}
export function hasToken(): boolean {
  return token !== null;
}
/** For the change socket, which authenticates via query param, not a header. */
export function getToken(): string | null {
  return token;
}

function setRefreshToken(t: string | null) {
  if (t) localStorage.setItem(REFRESH_KEY, t);
  else localStorage.removeItem(REFRESH_KEY);
}
function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY);
}

// --- errors ---

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

// --- request helper ---

async function request(
  path: string,
  init?: RequestInit,
  retry = true,
): Promise<Response> {
  const headers = new Headers(init?.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(path, { ...init, headers });
  if (res.status === 401 && retry && (await refreshAccessToken())) {
    return request(path, init, false); // retry once with the fresh access token
  }
  if (!res.ok) {
    throw new ApiError(
      res.status,
      `${init?.method ?? "GET"} ${path} → ${res.status}`,
    );
  }
  return res;
}

// --- auth ---

export async function register(
  username: string,
  password: string,
): Promise<void> {
  await request("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
}

export async function login(username: string, password: string): Promise<void> {
  const res = await request("/auth/login", {
    method: "POST",
    body: new URLSearchParams({ username, password }),
  });
  const data = (await res.json()) as {
    access_token: string;
    refresh_token: string;
  };
  setToken(data.access_token);
  setRefreshToken(data.refresh_token);
}

async function refreshAccessToken(): Promise<boolean> {
  const refresh = getRefreshToken();
  if (!refresh) return false;
  const res = await fetch("/auth/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refresh }),
  });
  if (!res.ok) {
    setRefreshToken(null); // refresh token dead/revoked → force a real re-login
    return false;
  }
  const data = (await res.json()) as { access_token: string };
  setToken(data.access_token);
  return true;
}

export async function logout(): Promise<void> {
  const refresh = getRefreshToken();
  if (refresh) {
    try {
      await request("/auth/logout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refresh }),
      });
    } catch {
      // best-effort: even if the call fails, clear local tokens below
    }
  }
  setToken(null);
  setRefreshToken(null);
}

export async function restoreSession(): Promise<boolean> {
  if (hasToken()) return true;
  return refreshAccessToken();
}

// --- files ---

export interface FileSummary {
  owner: string;
  path: string;
  size: number;
  updated_at: string;
  etag: string;
}

export interface Recipe {
  path: string;
  size: number;
  block_hashes: string[];
}

export async function listFiles(): Promise<FileSummary[]> {
  const res = await request("/files");
  const data = (await res.json()) as { files: FileSummary[] };
  return data.files;
}

export async function commit(
  name: string,
  size: number,
  block_hashes: string[],
  baseEtag?: string,
): Promise<string> {
  const path = "/" + name;
  const precondition: Record<string, string> = baseEtag
    ? { "If-Match": `"${baseEtag}"` }
    : { "If-None-Match": "*" };
  const res = await request("/files/commit", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...precondition },
    body: JSON.stringify({ path, size, block_hashes }),
  });
  return res.headers.get("ETag")?.replace(/"/g, "") ?? "";
}

export async function recipe(path: string, owner?: string): Promise<Recipe> {
  const url = new URL("/files/recipe", window.location.origin);
  url.searchParams.set("path", path);
  if (owner) url.searchParams.set("owner", owner);
  const res = await request(url.toString());
  return {
    ...(await res.json()),
    etag: res.headers.get("ETag")?.replace(/"/g, ""),
  };
}

export async function deleteFile(path: string): Promise<void> {
  const url = new URL("/files", window.location.origin);
  url.searchParams.set("path", path);
  await request(url.toString(), { method: "DELETE" });
}

// --- blocks ---

export async function missingBlocks(hashes: string[]): Promise<string[]> {
  const res = await request("/blocks/missing", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ hashes }),
  });
  const data = (await res.json()) as { missing: string[] };
  return data.missing;
}

export async function uploadUrls(
  hashes: string[],
): Promise<{ [hash: string]: string }> {
  const res = await request("/blocks/upload-urls", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ hashes }),
  });
  const data = (await res.json()) as { urls: { [hash: string]: string } };
  return data.urls;
}

export async function downloadUrls(
  hashes: string[],
  owner: string,
  path: string,
): Promise<Record<string, string>> {
  const url = new URL("/blocks/download-urls", window.location.origin);
  url.searchParams.set("owner", owner);
  url.searchParams.set("path", path);
  const res = await request(url.toString(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ hashes }),
  });
  const data = (await res.json()) as { urls: Record<string, string> };
  return data.urls;
}

// --- sharing ---

export interface Share {
  owner: string;
  path: string;
  shared_with: string;
  created_at: string;
}

export interface ShareLink {
  jti: string;
  owner: string;
  path: string;
  created_at: string;
  expires_at: string;
}

export async function shareWithUser(
  path: string,
  sharedWith: string,
): Promise<void> {
  await request("/shares", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, shared_with: sharedWith }),
  });
}

export async function revokeUserShare(
  path: string,
  sharedWith: string,
): Promise<void> {
  await request("/shares", {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, shared_with: sharedWith }),
  });
}

// files shared with me
export async function listIncomingShares(): Promise<Share[]> {
  const res = await request("/shares/incoming");
  return (await res.json()) as Share[];
}

// files i've shared
export async function listOutgoingShares(): Promise<Share[]> {
  const res = await request("/shares/outgoing");
  return (await res.json()) as Share[];
}

// --- share links ---

export async function createShareLink(path: string): Promise<string> {
  const res = await request("/shares/link", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
  const data = (await res.json()) as { token: string };
  return data.token;
}

export async function listShareLinks(): Promise<ShareLink[]> {
  const res = await request("/shares/link");
  const data = (await res.json()) as ShareLink[];
  return data;
}

export async function revokeShareLink(jti: string): Promise<void> {
  await request(`/shares/link/${jti}`, { method: "DELETE" });
}

export async function linkRecipe(token: string): Promise<Recipe> {
  const url = new URL("/link/recipe", window.location.origin);
  url.searchParams.set("token", token);
  const res = await request(url.toString());
  const data = (await res.json()) as Recipe;
  return data;
}

export async function linkDownloadUrls(
  token: string,
  hashes: string[],
): Promise<Record<string, string>> {
  const url = new URL("/link/download-urls", window.location.origin);
  url.searchParams.set("token", token);
  const res = await request(url.toString(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ hashes }),
  });
  const data = (await res.json()) as { urls: Record<string, string> };
  return data.urls;
}
