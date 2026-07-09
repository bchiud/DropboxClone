import { CircularProgress, Container } from "@mui/material";
import { useEffect, useState } from "react";
import { logout as apiLogout, hasToken, restoreSession } from "./api";
import { Login } from "./auth";
import { FileList } from "./files";
import { PublicDownload } from "./public";

export function App() {
  const [loggedIn, setLoggedIn] = useState(hasToken);
  const [restoring, setRestoring] = useState(true);
  const token = new URLSearchParams(window.location.search).get("token");

  useEffect(() => {
    if (token) {
      setRestoring(false); // public share link: no session to restore
      return;
    }
    restoreSession().then((ok) => {
      setLoggedIn(ok);
      setRestoring(false);
    });
  }, [token]);

  if (token) return <PublicDownload token={token} />;

  if (restoring)
    return (
      <Container maxWidth="sm" sx={{ mt: 8, textAlign: "center" }}>
        <CircularProgress />
      </Container>
    );

  async function logout() {
    await apiLogout();
    setLoggedIn(false);
  }

  return loggedIn ? (
    <FileList onLogout={logout} />
  ) : (
    <Login onLoggedIn={() => setLoggedIn(true)} />
  );
}
