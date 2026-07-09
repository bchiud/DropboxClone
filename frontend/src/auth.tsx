import { useState } from "react";
import { login, register, ApiError } from "./api";

export function Login({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(mode: "login" | "register") {
    setError(null);
    try {
      if (mode === "register") await register(username, password);
      await login(username, password); // register doesn't return a token, so log in after
      onLoggedIn(); // tell App we're in
    } catch (e) {
      if (e instanceof ApiError) {
        setError(
          e.status === 409 ? "Username taken" : "Invalid username or password",
        );
      } else {
        setError("Network error");
      }
    }
  }

  return (
    <div>
      <h1>Dropbox Clone</h1>
      <input
        placeholder="username"
        value={username}
        onChange={(e) => setUsername(e.target.value)}
      />
      <input
        type="password"
        placeholder="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />
      <button onClick={() => submit("login")}>Log in</button>
      <button onClick={() => submit("register")}>Register</button>
      {error && <p style={{ color: "red" }}>{error}</p>}
    </div>
  );
}
