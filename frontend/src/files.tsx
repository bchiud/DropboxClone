import CloudUploadIcon from "@mui/icons-material/CloudUpload";
import DeleteIcon from "@mui/icons-material/Delete";
import DownloadIcon from "@mui/icons-material/Download";
import ShareIcon from "@mui/icons-material/Share";
import {
  Alert,
  Box,
  Button,
  LinearProgress,
  Paper,
  Stack,
  Tooltip,
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
import { chunkFile } from "./crypto";
import { assembleBlocks, saveBlob } from "./download";
import {
  displayPath,
  downloadName,
  formatSize,
  middleTruncate,
} from "./format";
import { SharePanel } from "./shares";

export function FileList() {
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

      await commit(file.name, file.size, allHashes); // record the recipe
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
      const blob = await assembleBlocks(rec.block_hashes, urls);
      saveBlob(blob, downloadName(f.path));
    } catch (e) {
      console.error(e);
      setError(e instanceof Error ? e.message : "Download failed");
    } finally {
      setBusy(false);
    }
  }

  // --- remove ---
  async function remove(f: FileSummary) {
    if (!window.confirm(`Delete ${displayPath(f.path)}?`)) return;
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
    <>
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
              {/* minWidth:0 lets this flex item shrink below its content,
                  which is what allows the name to ellipsize */}
              <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                <Tooltip title={displayPath(f.path)} enterDelay={400}>
                  <Typography noWrap>
                    {middleTruncate(displayPath(f.path))}
                  </Typography>
                </Tooltip>
                <Typography variant="body2" color="text.secondary">
                  {formatSize(f.size)}
                </Typography>
              </Box>
              <Stack direction="row" spacing={1} sx={{ flexShrink: 0 }}>
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
            </Stack>
            {openPath === f.path && <SharePanel path={f.path} />}
          </Paper>
        ))}
      </Stack>
    </>
  );
}
