import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  CircularProgress,
  Container,
  LinearProgress,
  Stack,
  Typography,
} from "@mui/material";
import { linkDownloadUrls, linkRecipe, type Recipe } from "./api";
import { sha256Hex } from "./crypto";
import { formatSize } from "./format";

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
  if (error)
    return (
      <Container maxWidth="sm" sx={{ mt: 8 }}>
        <Alert severity="error">{error}</Alert>
      </Container>
    );
  if (!rec)
    return (
      <Container maxWidth="sm" sx={{ mt: 8 }}>
        <Stack direction="row" spacing={2} sx={{ alignItems: "center" }}>
          <CircularProgress size={20} />
          <Typography>Loading…</Typography>
        </Stack>
      </Container>
    );
  return (
    <Container maxWidth="sm" sx={{ mt: 8 }}>
      <Stack spacing={2}>
        <Typography variant="h4">Shared file</Typography>
        <Typography>
          {rec.path.replace(/^\//, "")} — {formatSize(rec.size)}
        </Typography>
        <Button
          variant="contained"
          onClick={download}
          disabled={busy}
          sx={{ alignSelf: "flex-start" }}
        >
          Download
        </Button>
        {busy && <LinearProgress />}
      </Stack>
    </Container>
  );
}
