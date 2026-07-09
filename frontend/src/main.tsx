import { StrictMode, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  createTheme,
  CssBaseline,
  IconButton,
  ThemeProvider,
} from "@mui/material";
import DarkModeIcon from "@mui/icons-material/DarkMode";
import LightModeIcon from "@mui/icons-material/LightMode";
import { App } from "./App";

function Root() {
  const [mode, setMode] = useState<"light" | "dark">(
    () =>
      (localStorage.getItem("mode") as "light" | "dark" | null) ??
      (window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light"),
  );

  useEffect(() => {
    localStorage.setItem("mode", mode);
  }, [mode]);

  const theme = useMemo(
    () =>
      createTheme({
        palette: {
          mode,
          primary: { main: "#00897b" }, // teal
          secondary: { main: "#ff7043" }, // coral accent
        },
      }),
    [mode],
  );

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <IconButton
        onClick={() => setMode((m) => (m === "light" ? "dark" : "light"))}
        sx={{
          position: "fixed",
          top: 8,
          right: 8,
          color: mode === "light" ? "#5c6bc0" : "#ffb300", // indigo moon / amber sun
        }}
      >
        {mode === "light" ? <DarkModeIcon /> : <LightModeIcon />}
      </IconButton>
      <App />
    </ThemeProvider>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);
