import {
  Alert,
  Box,
  Button,
  Container,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useState } from "react";
import { ApiError, login, register } from "./api";

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
    <Container maxWidth="xs">
      <Box sx={{ mt: 8 }}>
        <Stack spacing={2}>
          <Typography variant="h4" align="center">
            Dropbox Clone
          </Typography>
          <TextField
            label="Username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            fullWidth
          />
          <TextField
            label="Password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            fullWidth
          />
          <Button variant="contained" onClick={() => submit("login")}>
            Log in
          </Button>
          <Button variant="outlined" onClick={() => submit("register")}>
            Register
          </Button>
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </Box>
    </Container>
  );
}
