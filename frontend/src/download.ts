import { sha256Hex } from "./crypto";

export async function assembleBlocks(
  hashes: string[],
  urls: Record<string, string>,
): Promise<Blob> {
  const parts: ArrayBuffer[] = [];
  for (const hash of hashes) {
    // must be done in order. recipe order = file order
    const res = await fetch(urls[hash], { cache: "no-store" });
    if (!res.ok) throw new Error(`block GET ${hash} → ${res.status}`);
    const bytes = await res.arrayBuffer();
    if ((await sha256Hex(bytes)) !== hash)
      throw new Error(`block ${hash} failed verification`); // re-verify on read
    parts.push(bytes);
  }
  return new Blob(parts, { type: "application/octet-stream" });
}

// hand the assembled bytes to the browser as a file save.
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
