import { useState } from "react";
import { hasToken, setToken } from "./api";
import { Login } from "./auth";
import { FileList } from "./files";
import { PublicDownload } from "./public";

export function App() {
  const [loggedIn, setLoggedIn] = useState(hasToken);

  const token = new URLSearchParams(window.location.search).get("token");
  if (token) return <PublicDownload token={token} />;

  function logout() {
    setToken(null);
    setLoggedIn(false);
  }

  return loggedIn ? (
    <FileList onLogout={logout} />
  ) : (
    <Login onLoggedIn={() => setLoggedIn(true)} />
  );
}
