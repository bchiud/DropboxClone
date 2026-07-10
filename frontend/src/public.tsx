import {
  Alert,
  Button,
  CircularProgress,
  Container,
  LinearProgress,
  Stack,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";
import { linkDownloadUrls, linkRecipe, type Recipe } from "./api";
import { assembleBlocks, saveBlob } from "./download";
import { displayPath, downloadName, formatSize } from "./format";

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
      const blob = await assembleBlocks(rec.block_hashes, urls);
      saveBlob(blob, downloadName(rec.path));
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
          {displayPath(rec.path)} — {formatSize(rec.size)}
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
