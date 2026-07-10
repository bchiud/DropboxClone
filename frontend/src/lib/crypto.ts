export const BLOCK_SIZE = 4 * 1024 * 1024; // 4 MiB

export async function sha256Hex(bytes: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export interface Block {
  hash: string;
  blob: Blob; // the raw bytes, ready to PUT to B2
}

export async function chunkFile(file: File): Promise<Block[]> {
  const blocks: Block[] = [];
  for (let start = 0; start < file.size; start += BLOCK_SIZE) {
    const blob = file.slice(start, start + BLOCK_SIZE);
    const hash = await sha256Hex(await blob.arrayBuffer());
    blocks.push({ hash, blob });
  }
  return blocks;
}
