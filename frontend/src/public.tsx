import { useEffect, useState } from "react";
import { linkDownloadUrls, linkRecipe, type Recipe } from "./api";
import { sha256Hex } from "./crypto";

export function PublicDownload({ token }: { token: string }) {
  // --- state ---
  const [rec, setRec] = useState<Recipe | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // --- data loading ---
  useEffect(() => {
    async function load() {
      try {
        setRec(await linkRecipe(token));
      } catch {
        setError("This link is invalid or has expired.");
      }
    }
    load();
  }, [token]);

  // --- download ---
  async function download() {
    if (!rec) return;
    setBusy(true);
    setError(null);
    try {
      const urls = await linkDownloadUrls(token, rec.block_hashes);
      const parts: ArrayBuffer[] = [];
      for (const hash of rec.block_hashes) {
        const res = await fetch(urls[hash], { cache: "no-store" });
        if (!res.ok) throw new Error(`block GET ${hash} → ${res.status}`);
        const bytes = await res.arrayBuffer();
        if ((await sha256Hex(bytes)) !== hash)
          throw new Error(`block ${hash} failed verification`);
        parts.push(bytes);
      }
      const blob = new Blob(parts, { type: "application/octet-stream" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = rec.path.replace(/^\//, "");
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error(e);
      setError(e instanceof Error ? e.message : "Download failed");
    } finally {
      setBusy(false);
    }
  }

  // --- render ---
  if (error) return <p style={{ color: "red" }}>{error}</p>;
  if (!rec) return <p>Loading…</p>;
  return (
    <div>
      <h1>Shared file</h1>
      <p>
        {rec.path.replace(/^\//, "")} — {rec.size} bytes
      </p>
      <button onClick={download} disabled={busy}>
        Download
      </button>
      {busy && <p>Downloading…</p>}
    </div>
  );
}
