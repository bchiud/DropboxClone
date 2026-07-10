import DownloadIcon from "@mui/icons-material/Download";
import FolderSharedOutlinedIcon from "@mui/icons-material/FolderSharedOutlined";
import {
  Alert,
  Avatar,
  Box,
  Button,
  CircularProgress,
  Paper,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";
import {
  downloadUrls,
  listIncomingShares,
  recipe,
  type Share,
} from "./lib/api";
import { assembleBlocks, saveBlob } from "./lib/download";
import {
  displayPath,
  downloadName,
  formatDate,
  middleTruncate,
  userColor,
} from "./lib/format";

const shareKey = (s: Share) => `${s.owner}:${s.path}`;

const headCell = {
  textTransform: "uppercase",
  letterSpacing: "0.08em",
  fontSize: 11,
  fontWeight: 700,
  color: "text.secondary",
};

export function SharedWithMe() {
  const [incomingShares, setIncomingShares] = useState<Share[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyKey, setBusyKey] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        setIncomingShares(await listIncomingShares());
      } catch {
        setError("Could not load shared files");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  async function download(share: Share) {
    const { path, owner } = share;
    setBusyKey(shareKey(share));
    setError(null);
    try {
      const rec = await recipe(path, owner);
      const urls = await downloadUrls(rec.block_hashes, owner, path);
      const blob = await assembleBlocks(rec.block_hashes, urls);
      saveBlob(blob, downloadName(path));
    } catch (e) {
      console.error(e);
      setError(e instanceof Error ? e.message : "Download failed");
    } finally {
      setBusyKey(null);
    }
  }

  if (!loading && !error && incomingShares.length === 0) {
    return (
      <Paper
        variant="outlined"
        sx={{ p: 6, textAlign: "center", borderRadius: 2 }}
      >
        <FolderSharedOutlinedIcon
          sx={{ fontSize: 44, color: "text.disabled" }}
        />
        <Typography sx={{ mt: 1.5, fontWeight: 500 }}>
          Nothing shared with you yet
        </Typography>
        <Typography variant="body2" color="text.secondary">
          When someone shares a file with you, it appears here.
        </Typography>
      </Paper>
    );
  }

  return (
    <>
      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      <TableContainer
        component={Paper}
        variant="outlined"
        sx={{ borderRadius: 2 }}
      >
        {/* fixed layout: columns keep their width so a long name ellipsizes
            instead of shoving the other columns off the row */}
        <Table size="small" sx={{ tableLayout: "fixed" }}>
          <TableHead>
            <TableRow sx={{ bgcolor: "action.hover" }}>
              <TableCell sx={headCell}>Name</TableCell>
              <TableCell sx={{ ...headCell, width: 120 }}>Shared by</TableCell>
              <TableCell sx={{ ...headCell, width: 120 }}>Shared on</TableCell>
              <TableCell sx={{ ...headCell, width: 140 }} align="right">
                Actions
              </TableCell>
            </TableRow>
          </TableHead>

          <TableBody>
            {loading &&
              [0, 1, 2].map((i) => (
                <TableRow key={i}>
                  <TableCell colSpan={4}>
                    <Skeleton height={28} />
                  </TableCell>
                </TableRow>
              ))}

            {incomingShares.map((s) => {
              const busy = busyKey === shareKey(s);
              return (
                <TableRow
                  key={shareKey(s)}
                  sx={{
                    "&:last-child td": { border: 0 },
                    "&:hover": { bgcolor: "action.hover" },
                  }}
                >
                  <TableCell sx={{ fontWeight: 500 }}>
                    <Tooltip title={displayPath(s.path)} enterDelay={400}>
                      <Box
                        sx={{
                          flexGrow: 1,
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {middleTruncate(displayPath(s.path))}
                      </Box>
                    </Tooltip>
                  </TableCell>

                  <TableCell>
                    <Box
                      sx={{
                        display: "flex",
                        alignItems: "center",
                        gap: 1.25,
                        minWidth: 0,
                      }}
                    >
                      <Avatar
                        sx={{
                          width: 26,
                          height: 26,
                          fontSize: 12,
                          fontWeight: 600,
                          bgcolor: userColor(s.owner),
                        }}
                      >
                        {s.owner.charAt(0).toUpperCase()}
                      </Avatar>
                      <Box
                        sx={{
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {s.owner}
                      </Box>
                    </Box>
                  </TableCell>

                  <TableCell sx={{ color: "text.secondary" }}>
                    {formatDate(s.created_at)}
                  </TableCell>

                  <TableCell align="right">
                    <Button
                      size="small"
                      startIcon={
                        busy ? (
                          <CircularProgress size={14} color="inherit" />
                        ) : (
                          <DownloadIcon />
                        )
                      }
                      onClick={() => download(s)}
                      disabled={busy}
                    >
                      Download
                    </Button>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>
    </>
  );
}
