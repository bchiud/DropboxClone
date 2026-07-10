// The realtime change socket (`/ws`). The server pushes {"type":"changed"} to a
// user's devices whenever something they can see changes; the payload carries no
// data, so every handler here just refetches.
import { getToken } from "./api";

const RETRY_BASE_MS = 1000;
const RETRY_CAP_MS = 30_000;
const RETRY_JITTER_MS = 250;

/**
 * Subscribe to change events for the current user. Returns a disposer — the
 * socket is replaced on every reconnect, so callers must never hold it.
 */
export function connectChanges(onChange: () => void): () => void {
  let ws: WebSocket | null = null;
  let timer: number | undefined;
  let retry = 0;
  let disposed = false;

  function open() {
    const url = new URL("/ws", window.location.origin);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    url.searchParams.set("token", getToken() ?? ""); // re-read: may have refreshed
    ws = new WebSocket(url.toString());

    ws.onopen = () => {
      // Notifications sent while we were away are gone — nothing replays them.
      if (retry > 0) onChange();
      retry = 0;
    };
    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (msg.type === "changed") onChange();
    };
    ws.onclose = () => {
      if (disposed) return; // our own close(), not a drop
      const backoff = Math.min(RETRY_BASE_MS * 2 ** retry++, RETRY_CAP_MS);
      timer = window.setTimeout(
        open,
        backoff + Math.random() * RETRY_JITTER_MS,
      );
    };
  }

  open();
  return () => {
    disposed = true; // set first: ws.close() below fires onclose
    window.clearTimeout(timer);
    ws?.close();
  };
}
