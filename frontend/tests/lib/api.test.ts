import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, commit } from "../../src/lib/api";

/** Capture what the client sends and reply with a chosen status + ETag. */
function stubFetch(status: number, etag?: string) {
  const calls: { url: string; init: RequestInit }[] = [];
  const fetchMock = vi.fn(async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return {
      ok: status >= 200 && status < 300,
      status,
      headers: { get: (k: string) => (k === "ETag" ? (etag ?? null) : null) },
    };
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

afterEach(() => vi.unstubAllGlobals());

describe("commit precondition headers", () => {
  it("creates with If-None-Match: * when there is no base etag", async () => {
    const calls = stubFetch(201, '"new-etag"');
    const etag = await commit("a.txt", 5, ["h1"]);
    const headers = calls[0].init.headers as Headers;
    expect(headers.get("If-None-Match")).toBe("*");
    expect(headers.get("If-Match")).toBeNull();
    expect(etag).toBe("new-etag"); // quotes stripped, ready to store
  });

  it("updates with If-Match: <base> when a base etag is supplied", async () => {
    const calls = stubFetch(200, '"new-etag"');
    await commit("a.txt", 5, ["h1"], "base-etag");
    const headers = calls[0].init.headers as Headers;
    expect(headers.get("If-Match")).toBe('"base-etag"');
    expect(headers.get("If-None-Match")).toBeNull();
  });

  it("surfaces a 412 as ApiError so the UI can prompt to reconcile", async () => {
    stubFetch(412);
    await expect(commit("a.txt", 5, ["h1"], "stale")).rejects.toBeInstanceOf(
      ApiError,
    );
  });
});
