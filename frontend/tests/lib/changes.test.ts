/**
 * Unit tests for connectChanges — the /ws change socket.
 *
 * Runs in the node environment, so `window` and `WebSocket` are stubbed. Timers
 * are faked and Math.random is pinned, making the backoff schedule exact.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { setToken } from "../../src/lib/api";
import { connectChanges } from "../../src/lib/changes";

/** Stands in for the browser WebSocket; every instance is recorded. */
class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static get last(): FakeWebSocket {
    return FakeWebSocket.instances[FakeWebSocket.instances.length - 1];
  }

  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  closed = false;

  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }

  // the real WebSocket fires onclose when the caller closes it, too
  close(): void {
    this.closed = true;
    this.onclose?.();
  }

  // --- test drivers ---
  accept(): void {
    this.onopen?.();
  }
  deliver(payload: unknown): void {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }
  drop(): void {
    this.onclose?.();
  }
}

const FIRST_DELAY = 1000; // 1000 * 2**0
const JITTER = 250;

beforeEach(() => {
  FakeWebSocket.instances = [];
  vi.stubGlobal("WebSocket", FakeWebSocket);
  vi.stubGlobal("window", {
    location: { origin: "http://localhost:5173" },
    // delegate, so vi.useFakeTimers() patches take effect
    setTimeout: (fn: () => void, ms: number) => globalThis.setTimeout(fn, ms),
    clearTimeout: (id: number) => globalThis.clearTimeout(id),
  });
  vi.useFakeTimers();
  vi.spyOn(Math, "random").mockReturnValue(0); // no jitter unless a test asks
  setToken("tok-1");
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  setToken(null);
});

describe("connecting", () => {
  it("opens a socket immediately, over ws:// with the token in the query", () => {
    connectChanges(() => {});
    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(FakeWebSocket.last.url).toBe("ws://localhost:5173/ws?token=tok-1");
  });

  it("invokes onChange for a `changed` frame and ignores anything else", () => {
    const onChange = vi.fn();
    connectChanges(onChange);
    FakeWebSocket.last.deliver({ type: "hello" });
    expect(onChange).not.toHaveBeenCalled();
    FakeWebSocket.last.deliver({ type: "changed" });
    expect(onChange).toHaveBeenCalledTimes(1);
  });
});

describe("reconnecting", () => {
  it("reopens after a drop, once the backoff elapses", () => {
    connectChanges(() => {});
    FakeWebSocket.last.drop();
    expect(FakeWebSocket.instances).toHaveLength(1); // not synchronously

    vi.advanceTimersByTime(FIRST_DELAY - 1);
    expect(FakeWebSocket.instances).toHaveLength(1);

    vi.advanceTimersByTime(1);
    expect(FakeWebSocket.instances).toHaveLength(2);
  });

  it("backs off exponentially while reconnects keep failing", () => {
    connectChanges(() => {});
    FakeWebSocket.last.drop();
    vi.advanceTimersByTime(1000); // 2**0
    expect(FakeWebSocket.instances).toHaveLength(2);

    FakeWebSocket.last.drop();
    vi.advanceTimersByTime(1999); // 2**1 = 2000
    expect(FakeWebSocket.instances).toHaveLength(2);
    vi.advanceTimersByTime(1);
    expect(FakeWebSocket.instances).toHaveLength(3);

    FakeWebSocket.last.drop();
    vi.advanceTimersByTime(3999); // 2**2 = 4000
    expect(FakeWebSocket.instances).toHaveLength(3);
    vi.advanceTimersByTime(1);
    expect(FakeWebSocket.instances).toHaveLength(4);
  });

  it("caps the backoff at 30s rather than growing without bound", () => {
    connectChanges(() => {});
    for (let i = 0; i < 12; i++) {
      // 2**12 s would be ~68 minutes if uncapped
      FakeWebSocket.last.drop();
      vi.advanceTimersByTime(30_000);
    }
    expect(FakeWebSocket.instances).toHaveLength(13);
  });

  it("resets the backoff once a connection succeeds", () => {
    connectChanges(() => {});
    FakeWebSocket.last.drop();
    vi.advanceTimersByTime(1000);
    FakeWebSocket.last.drop();
    vi.advanceTimersByTime(2000); // now at 2**1
    FakeWebSocket.last.accept(); // ...and it sticks

    FakeWebSocket.last.drop();
    vi.advanceTimersByTime(1000); // back to 2**0, not 2**2
    expect(FakeWebSocket.instances).toHaveLength(4);
  });

  it("spreads the herd with jitter on top of the delay", () => {
    (Math.random as ReturnType<typeof vi.fn>).mockReturnValue(1);
    connectChanges(() => {});
    FakeWebSocket.last.drop();

    vi.advanceTimersByTime(FIRST_DELAY + JITTER - 1);
    expect(FakeWebSocket.instances).toHaveLength(1); // jitter still pending
    vi.advanceTimersByTime(1);
    expect(FakeWebSocket.instances).toHaveLength(2);
  });

  it("re-reads the token, so a refresh mid-outage is picked up", () => {
    connectChanges(() => {});
    FakeWebSocket.last.drop();
    setToken("tok-2");
    vi.advanceTimersByTime(FIRST_DELAY);
    expect(FakeWebSocket.last.url).toContain("token=tok-2");
  });
});

describe("missed events", () => {
  it("refetches on reconnect, since notifications sent while away are gone", () => {
    const onChange = vi.fn();
    connectChanges(onChange);
    FakeWebSocket.last.accept();
    expect(onChange).not.toHaveBeenCalled(); // first open: caller already fetched

    FakeWebSocket.last.drop();
    vi.advanceTimersByTime(FIRST_DELAY);
    FakeWebSocket.last.accept();
    expect(onChange).toHaveBeenCalledTimes(1); // the view may be stale
  });
});

describe("disposing", () => {
  it("closes the live socket", () => {
    const stop = connectChanges(() => {});
    const ws = FakeWebSocket.last;
    stop();
    expect(ws.closed).toBe(true);
  });

  it("does not resurrect the socket that its own close() just killed", () => {
    // close() fires onclose, which is exactly the path that schedules a reconnect.
    // Without a disposed guard this leaks an immortal socket -- and React StrictMode
    // mounts/unmounts every component once, so it would fire on the first page load.
    const stop = connectChanges(() => {});
    stop();
    vi.advanceTimersByTime(60_000);
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("cancels a reconnect already scheduled", () => {
    const stop = connectChanges(() => {});
    FakeWebSocket.last.drop(); // reconnect armed
    stop(); // ...disarm it
    vi.advanceTimersByTime(60_000);
    expect(FakeWebSocket.instances).toHaveLength(1);
  });
});
