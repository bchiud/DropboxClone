import CloudUploadIcon from "@mui/icons-material/CloudUpload";
import DeleteIcon from "@mui/icons-material/Delete";
import DownloadIcon from "@mui/icons-material/Download";
import LogoutIcon from "@mui/icons-material/Logout";
import ShareIcon from "@mui/icons-material/Share";
import {
  Alert,
  Box,
  Button,
  Container,
  LinearProgress,
  Paper,
  Stack,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";
import {
  commit,
  connectChanges,
  deleteFile,
  downloadUrls,
  listFiles,
  missingBlocks,
  recipe,
  uploadUrls,
  type FileSummary,
} from "./api";
import { chunkFile, sha256Hex } from "./crypto";
import { formatSize } from "./format";
import { SharePanel } from "./shares";

export function FileList({ onLogout }: { onLogout: () => void }) {
  // --- state ---
  const [files, setFiles] = useState<FileSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [openPath, setOpenPath] = useState<string | null>(null);

  // --- data loading ---
  async function refresh() {
    try {
      setFiles(await listFiles());
    } catch {
      setError("Could not load files");
    }
  }

  useEffect(() => {
    refresh(); // initial load on mount
    const ws = connectChanges(() => refresh()); // + live updates after
    return () => ws.close();
  }, []);

  // --- upload ---
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

  // --- download ---
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

      const blob = new Blob(parts, { type: "application/octet-stream" });
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

  // --- remove ---
  async function remove(f: FileSummary) {
    if (!window.confirm(`Delete ${f.path}?`)) return;
    setBusy(true);
    setError(null);
    try {
      await deleteFile(f.path);
      await refresh();
    } catch {
      setError("Delete failed");
    } finally {
      setBusy(false);
    }
  }

  // --- render ---
  function toggleShare(path: string) {
    setOpenPath(openPath === path ? null : path);
  }

  return (
    <Container maxWidth="sm" sx={{ mt: 4 }}>
      <Stack direction="row" sx={{ alignItems: "center", mb: 2 }}>
        <Typography variant="h5" sx={{ flexGrow: 1 }}>
          Your files
        </Typography>
        <Button startIcon={<LogoutIcon />} onClick={onLogout}>
          Log out
        </Button>
      </Stack>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      <Button
        variant="contained"
        component="label"
        disabled={busy}
        startIcon={<CloudUploadIcon />}
        sx={{ mb: 1 }}
      >
        Upload file
        <input
          type="file"
          hidden
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) upload(file);
          }}
        />
      </Button>
      {busy && <LinearProgress sx={{ mb: 2 }} />}

      <Stack spacing={1}>
        {files.map((f) => (
          <Paper key={f.path} variant="outlined" sx={{ p: 1 }}>
            <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
              <Box sx={{ flexGrow: 1 }}>
                <Typography>{f.path}</Typography>
                <Typography variant="body2" color="text.secondary">
                  {formatSize(f.size)}
                </Typography>
              </Box>
              <Button
                size="small"
                startIcon={<DownloadIcon />}
                onClick={() => download(f)}
                disabled={busy}
              >
                Download
              </Button>
              <Button
                size="small"
                startIcon={<ShareIcon />}
                onClick={() => toggleShare(f.path)}
              >
                Share
              </Button>
              <Button
                size="small"
                startIcon={<DeleteIcon />}
                onClick={() => remove(f)}
                disabled={busy}
                sx={{ color: "error.light" }}
              >
                Delete
              </Button>
            </Stack>
            {openPath === f.path && <SharePanel path={f.path} />}
          </Paper>
        ))}
      </Stack>
    </Container>
  );
}
