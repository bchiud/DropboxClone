// --- client state (auth token) ---

let token: string | null = null;
export function setToken(t: string | null) {
  token = t;
}

export function hasToken(): boolean {
  return token !== null;
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

async function request(path: string, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(path, { ...init, headers });
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
  const data = (await res.json()) as { access_token: string };
  setToken(data.access_token);
}

// --- files ---

export interface FileSummary {
  owner: string;
  path: string;
  size: number;
  updated_at: string;
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
  path: string,
  size: number,
  block_hashes: string[],
): Promise<void> {
  await request("/files/commit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, size, block_hashes }),
  });
}

export async function recipe(path: string, owner?: string): Promise<Recipe> {
  const url = new URL("/files/recipe", window.location.origin);
  url.searchParams.set("path", path);
  if (owner) url.searchParams.set("owner", owner);
  const res = await request(url.toString());
  const data = (await res.json()) as Recipe;
  return data;
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

// --- real time ---
export function connectChanges(onChange: () => void): WebSocket {
  const url = new URL("/ws", window.location.origin);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.searchParams.set("token", token ?? "");
  const ws = new WebSocket(url.toString());
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === "changed") onChange();
  };
  return ws;
}
