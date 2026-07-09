import { useEffect, useState } from "react";
import {
  commit,
  downloadUrls,
  listFiles,
  missingBlocks,
  recipe,
  uploadUrls,
  type FileSummary,
} from "./api";
import { chunkFile, sha256Hex } from "./crypto";

export function FileList({ onLogout }: { onLogout: () => void }) {
  const [files, setFiles] = useState<FileSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [busy, setBusy] = useState(false);

  async function refresh() {
    try {
      setFiles(await listFiles());
    } catch {
      setError("Could not load files");
    }
  }

  async function upload(file: File) {
    setBusy(true);
    setError(null);
    try {
      const blocks = await chunkFile(file); // [{hash, blob}, ...]
      const allHashes = blocks.map((b) => b.hash); // full recipe, in order
      const missing = await missingBlocks(allHashes); // what the server lacks
      const toSend = blocks.filter((b) => missing.includes(b.hash));

      const urls = toSend.length ? await uploadUrls(missing) : {};
      await Promise.all(
        toSend.map(async (b) => {
          const res = await fetch(urls[b.hash], {
            method: "PUT",
            body: b.blob,
          });
          if (!res.ok) throw new Error(`block PUT ${b.hash} → ${res.status}`);
        }),
      );

      await commit("/" + file.name, file.size, allHashes); // record the recipe
      await refresh(); // reload the list
    } catch {
      setError("Upload failed");
    } finally {
      setBusy(false);
    }
  }
  async function download(f: FileSummary) {
    setBusy(true);
    setError(null);
    try {
      const rec = await recipe(f.path, f.owner);
      const urls = await downloadUrls(rec.block_hashes, f.owner, f.path);

      const parts: ArrayBuffer[] = [];
      for (const hash of rec.block_hashes) {
        // IN ORDER — recipe order = file order
        const res = await fetch(urls[hash], { cache: "no-store" }); // plain fetch to B2 again
        if (!res.ok) throw new Error(`block GET ${hash} → ${res.status}`);
        const bytes = await res.arrayBuffer();
        if ((await sha256Hex(bytes)) !== hash)
          // re-verify on read
          throw new Error(`block ${hash} failed verification`);
        parts.push(bytes);
      }

      const blob = new Blob(parts);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = f.path.replace(/^\//, ""); // "/foo.txt" -> "foo.txt"
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error(e);
      setError(e instanceof Error ? e.message : "Download failed");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  return (
    <div>
      <h2>Your files</h2>
      <button onClick={onLogout}>Log out</button>
      {error && <p style={{ color: "red" }}>{error}</p>}
      <input
        type="file"
        disabled={busy}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) upload(file);
        }}
      />
      {busy && <p>Working…</p>}
      <ul>
        {files.map((f) => (
          <li key={f.path}>
            {f.path} — {f.size} bytes{" "}
            <button onClick={() => download(f)} disabled={busy}>
              Download
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
