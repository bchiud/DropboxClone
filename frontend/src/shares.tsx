import AddLinkIcon from "@mui/icons-material/AddLink";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import DeleteIcon from "@mui/icons-material/Delete";
import PersonAddIcon from "@mui/icons-material/PersonAdd";
import {
  Alert,
  Avatar,
  Box,
  Button,
  Chip,
  Divider,
  IconButton,
  InputAdornment,
  List,
  ListItem,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";
import { connectChanges } from "./lib/changes";
import {
  createShareLink,
  listOutgoingShares,
  listShareLinks,
  revokeShareLink,
  revokeUserShare,
  shareWithUser,
  type Share,
  type ShareLink,
} from "./lib/api";
import { userColor } from "./lib/format";

export function SharePanel({ path }: { path: string }) {
  // --- state ---
  const [recipient, setRecipient] = useState("");
  const [links, setLinks] = useState<ShareLink[]>([]);
  const [grants, setGrants] = useState<Share[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [linkUrl, setLinkUrl] = useState<string | null>(null);
  const [busyChip, setBusyChip] = useState<string | null>(null);

  // --- data loading ---
  async function refreshLinks() {
    const all = await listShareLinks();
    setLinks(all.filter((l) => l.path === path)); // only THIS file's links
  }

  async function refreshGrants() {
    const all = await listOutgoingShares();
    setGrants(all.filter((g) => g.path === path)); // only THIS file's grants
  }

  useEffect(() => {
    refreshLinks();
    refreshGrants();
    return connectChanges(() => {
      refreshLinks();
      refreshGrants();
    });
  }, [path]);

  // --- actions ---
  async function grant() {
    try {
      await shareWithUser(path, recipient);
      setStatus(`Shared with ${recipient}`);
      setRecipient("");
      await refreshGrants();
    } catch {
      setStatus("Could not share");
    }
  }

  async function revokeGrant(sharedWith: string) {
    setBusyChip(sharedWith);
    try {
      await revokeUserShare(path, sharedWith);
      setStatus(`Stopped sharing with ${sharedWith}`);
      await refreshGrants();
    } catch {
      setStatus("Could not revoke");
    } finally {
      setBusyChip(null);
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

      <Box sx={{ mb: 1.5 }}>
        <Typography variant="caption" color="text.secondary">
          Shared with
        </Typography>
        {grants.length === 0 ? (
          <Typography variant="body2" color="text.disabled">
            No one yet
          </Typography>
        ) : (
          <Stack
            direction="row"
            spacing={0.75}
            sx={{ flexWrap: "wrap", mt: 0.5 }}
          >
            {grants.map((g) => (
              <Tooltip
                key={g.shared_with}
                title={`Stop sharing with ${g.shared_with}`}
              >
                <Chip
                  size="small"
                  label={g.shared_with}
                  disabled={busyChip === g.shared_with}
                  onDelete={() => revokeGrant(g.shared_with)}
                  avatar={
                    <Avatar sx={{ bgcolor: userColor(g.shared_with) }}>
                      {g.shared_with.charAt(0).toUpperCase()}
                    </Avatar>
                  }
                />
              </Tooltip>
            ))}
          </Stack>
        )}
      </Box>

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
