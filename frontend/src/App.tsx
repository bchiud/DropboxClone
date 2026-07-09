import { useState } from "react";
import { hasToken, setToken } from "./api";
import { Login } from "./auth";
import { FileList } from "./files";

export function App() {
  const [loggedIn, setLoggedIn] = useState(hasToken);

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
