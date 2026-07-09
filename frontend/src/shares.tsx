import { useEffect, useState } from "react";
import {
  createShareLink,
  listShareLinks,
  revokeShareLink,
  ShareLink,
  shareWithUser,
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
    <div
      style={{
        margin: "0.5rem 0",
        padding: "0.5rem",
        border: "1px solid #ccc",
      }}
    >
      {status && <p>{status}</p>}

      <div>
        <input
          placeholder="username"
          value={recipient}
          onChange={(e) => setRecipient(e.target.value)}
        />
        <button onClick={grant} disabled={!recipient}>
          Share with user
        </button>
      </div>

      <div>
        <button onClick={makeLink}>Make public link</button>
        {linkUrl && (
          <input
            readOnly
            value={linkUrl}
            onFocus={(e) => e.target.select()}
            style={{ width: "100%" }}
          />
        )}
      </div>

      <ul>
        {links.map((l) => (
          <li key={l.jti}>
            {l.jti.slice(0, 8)}… expires{" "}
            {new Date(l.expires_at).toLocaleString()}{" "}
            <button onClick={() => revoke(l.jti)}>Revoke</button>
          </li>
        ))}
      </ul>
    </div>
  );
}
