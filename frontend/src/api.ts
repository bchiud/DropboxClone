let token: string | null = null;
export function setToken(t: string | null) {
  token = t;
}

export function hasToken(): boolean {
  return token !== null;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

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

export async function listFiles(): Promise<FileSummary[]> {
  const res = await request("/files");
  const data = (await res.json()) as { files: FileSummary[] };
  return data.files;
}

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
