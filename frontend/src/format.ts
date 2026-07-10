export function displayPath(path: string): string {
  return path.replace(/^\//, "");
}

export function downloadName(path: string): string {
  return path.slice(path.lastIndexOf("/") + 1);
}

// Human-readable byte sizes: 500 -> "500 B", 1536 -> "1.5 KB", 5_000_000 -> "4.8 MB".
const UNITS = ["B", "KB", "MB", "GB", "TB"];

export function formatSize(bytes: number): string {
  let n = bytes;
  let i = 0;
  while (n >= 1024 && i < UNITS.length - 1) {
    n /= 1024;
    i += 1;
  }
  return `${n.toFixed(i === 0 ? 0 : 1)} ${UNITS[i]}`; // no decimals for plain bytes
}
