import LogoutIcon from "@mui/icons-material/Logout";
import { Button, Container, Stack, Tab, Tabs, Typography } from "@mui/material";
import { useState } from "react";
import { FileList } from "./files";
import { SharedWithMe } from "./shared";

export function Home({ onLogout }: { onLogout: () => void }) {
  const [tab, setTab] = useState(0);

  return (
    <Container maxWidth={false} sx={{ maxWidth: 750, mt: 4 }}>
      <Stack direction="row" sx={{ alignItems: "center", mb: 2 }}>
        <Typography variant="h5" sx={{ flexGrow: 1 }}>
          Dropbox Clone
        </Typography>
        <Button startIcon={<LogoutIcon />} onClick={onLogout}>
          Log out
        </Button>
      </Stack>

      <Tabs value={tab} onChange={(_, next) => setTab(next)} sx={{ mb: 2 }}>
        <Tab label="Your files" />
        <Tab label="Shared with you" />
      </Tabs>

      {tab === 0 ? <FileList /> : <SharedWithMe />}
    </Container>
  );
}
