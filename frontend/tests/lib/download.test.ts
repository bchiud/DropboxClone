import { afterEach, describe, expect, it, vi } from "vitest";
import { assembleBlocks } from "../../src/lib/download";

// Digests computed independently of the code under test — don't hash with the
// same helper you're verifying. Reproduce any of these with:
//   printf '%s' 'hello ' | shasum -a 256
const HASH = {
  "hello ": "5e3235a8346e5a4585f8c58562f5052b8fe26a3bb122e1e96c76784964dfc461",
  "shared world":
    "890a4b5807f957b629008c14c0aa4468a395612919997110d7074ff204bac982",
  x: "2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881",
  "the real bytes":
    "1ca6e2bee4940c063caac8f168f9b44a48e5b44c1d98ffa1c5cb20faee0a0bab",
  first: "a7937b64b8caa58f03721bb6bacf5c78cb235febe0e70b1b84cd99541461a08e",
  second: "16367aacb67a4a017c8da8ab95682ccb390863780f7114dda0a0e0c55644c7c4",
} as const;

const bytesOf = (text: string) => new TextEncoder().encode(text);

/** Serve each url the bytes registered for it. */
function stubFetch(bodies: Record<string, string>, ok = true, status = 200) {
  const fetchMock = vi.fn(async (url: string) => ({
    ok,
    status,
    arrayBuffer: async () => bytesOf(bodies[url]).buffer,
  }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

describe("assembleBlocks", () => {
  it("reassembles blocks in recipe order, not url-map order", async () => {
    // urls deliberately declares the second block first — iteration order of the
    // map must not leak into the byte order of the file.
    const urls = {
      [HASH["shared world"]]: "u-b",
      [HASH["hello "]]: "u-a",
    };
    const fetchMock = stubFetch({ "u-a": "hello ", "u-b": "shared world" });

    const blob = await assembleBlocks(
      [HASH["hello "], HASH["shared world"]],
      urls,
    );

    expect(await blob.text()).toBe("hello shared world");
    expect(fetchMock.mock.calls.map((c) => c[0])).toEqual(["u-a", "u-b"]);
  });

  it("labels the blob as opaque bytes", async () => {
    stubFetch({ "u-a": "x" });
    const blob = await assembleBlocks([HASH.x], { [HASH.x]: "u-a" });
    expect(blob.type).toBe("application/octet-stream");
  });

  it("bypasses the http cache, so a stale block can't be served", async () => {
    const fetchMock = stubFetch({ "u-a": "x" });
    await assembleBlocks([HASH.x], { [HASH.x]: "u-a" });
    expect(fetchMock).toHaveBeenCalledWith("u-a", { cache: "no-store" });
  });

  it("rejects a block whose bytes don't match its hash", async () => {
    stubFetch({ "u-a": "tampered bytes" }); // served under the real block's hash

    await expect(
      assembleBlocks([HASH["the real bytes"]], {
        [HASH["the real bytes"]]: "u-a",
      }),
    ).rejects.toThrow(`block ${HASH["the real bytes"]} failed verification`);
  });

  it("rejects a failed block fetch", async () => {
    stubFetch({ "u-a": "x" }, false, 403);

    await expect(assembleBlocks([HASH.x], { [HASH.x]: "u-a" })).rejects.toThrow(
      `block GET ${HASH.x} → 403`,
    );
  });

  it("stops at the first bad block instead of downloading the rest", async () => {
    const fetchMock = stubFetch({ "u-a": "tampered", "u-b": "second" });

    await expect(
      assembleBlocks([HASH.first, HASH.second], {
        [HASH.first]: "u-a",
        [HASH.second]: "u-b",
      }),
    ).rejects.toThrow(/failed verification/);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("returns an empty blob for an empty recipe", async () => {
    stubFetch({});
    const blob = await assembleBlocks([], {});
    expect(blob.size).toBe(0);
  });
});
