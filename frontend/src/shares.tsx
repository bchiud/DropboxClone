import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Divider,
  IconButton,
  InputAdornment,
  List,
  ListItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import AddLinkIcon from "@mui/icons-material/AddLink";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import DeleteIcon from "@mui/icons-material/Delete";
import PersonAddIcon from "@mui/icons-material/PersonAdd";
import {
  createShareLink,
  listShareLinks,
  revokeShareLink,
  shareWithUser,
  type ShareLink,
} from "./api";

export function SharePanel({ path }: { path: string }) {
  // --- state ---
  const [recipient, setRecipient] = useState("");
  const [links, setLinks] = useState<ShareLink[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [linkUrl, setLinkUrl] = useState<string | null>(null);

  // --- data loading ---
  async function refreshLinks() {
    const all = await listShareLinks();
    setLinks(all.filter((l) => l.path === path)); // only THIS file's links
  }

  useEffect(() => {
    refreshLinks();
  }, [path]);

  // --- actions ---
  async function grant() {
    try {
      await shareWithUser(path, recipient);
      setStatus(`Shared with ${recipient}`);
      setRecipient("");
    } catch {
      setStatus("Could not share");
    }
  }

  async function makeLink() {
    try {
      const token = await createShareLink(path);
      const url = `${window.location.origin}/?token=${token}`;
      setLinkUrl(url);
      await navigator.clipboard.writeText(url);
      setStatus("Link copied to clipboard");
      await refreshLinks();
    } catch {
      setStatus("Could not create link");
    }
  }

  async function copyLink() {
    if (!linkUrl) return;
    await navigator.clipboard.writeText(linkUrl);
    setStatus("Link copied to clipboard");
  }

  async function revoke(jti: string) {
    try {
      await revokeShareLink(jti);
      await refreshLinks();
    } catch {
      setStatus("Could not revoke");
    }
  }

  // --- render ---
  return (
    <Box sx={{ mt: 1 }}>
      <Divider sx={{ mb: 1 }} />

      {status && (
        <Alert severity="info" sx={{ mb: 1 }}>
          {status}
        </Alert>
      )}

      <Stack direction="row" spacing={1} sx={{ mb: 1 }}>
        <TextField
          size="small"
          label="username"
          value={recipient}
          onChange={(e) => setRecipient(e.target.value)}
        />
        <Button
          variant="outlined"
          startIcon={<PersonAddIcon />}
          onClick={grant}
          disabled={!recipient}
        >
          Share with user
        </Button>
      </Stack>

      <Stack spacing={1} sx={{ mb: 1 }}>
        <Button
          variant="outlined"
          startIcon={<AddLinkIcon />}
          onClick={makeLink}
          sx={{ alignSelf: "flex-start" }}
        >
          Make public link
        </Button>
        {linkUrl && (
          <TextField
            size="small"
            value={linkUrl}
            onFocus={(e) => e.target.select()}
            fullWidth
            slotProps={{
              input: {
                readOnly: true,
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton edge="end" size="small" onClick={copyLink}>
                      <ContentCopyIcon fontSize="small" />
                    </IconButton>
                  </InputAdornment>
                ),
              },
            }}
          />
        )}
      </Stack>

      {links.length > 0 && (
        <List dense disablePadding>
          {links.map((l) => (
            <ListItem
              key={l.jti}
              disableGutters
              secondaryAction={
                <Button
                  size="small"
                  color="error"
                  startIcon={<DeleteIcon />}
                  onClick={() => revoke(l.jti)}
                >
                  Revoke
                </Button>
              }
            >
              <Typography variant="body2">
                {l.jti.slice(0, 8)}… expires{" "}
                {new Date(l.expires_at).toLocaleString()}
              </Typography>
            </ListItem>
          ))}
        </List>
      )}
    </Box>
  );
}
