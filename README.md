# Dropbox Clone

A content-addressed file storage & sync system, built as a learning project.
It has two parts: a **FastAPI server** that stores files as hash-addressed blocks,
and a **sync client** — a folder-watching daemon that pushes/pulls changes, like
the Dropbox desktop app.

- **Server API:** FastAPI (Python 3.12)
- **Blocks:** Backblaze B2 (S3-compatible)
- **Metadata:** MongoDB Atlas
- **Auth:** JWT (HS256) + bcrypt
- **Client:** watchdog folder watcher + httpx

---

## Core idea: content-addressed storage

Every file is split into fixed-size blocks (4 MiB). Each block is stored under
the **SHA-256 hash of its contents** — the key *is* the hash. A file is then just
an ordered list of block hashes (its "recipe"), stored as metadata.

```
file bytes ──chunk──▶ [block, block, block]
                         │      │      │
                       sha256 sha256 sha256
                         ▼      ▼      ▼
   recipe:  ["3af…", "9c1…", "70b…"]     ← stored in MongoDB
   blocks:  key=<owner>/<hash> → bytes   ← stored in B2
```

This buys three things:

- **Deduplication** — identical blocks are stored once **per user** (see scoping below).
- **Delta sync** — editing part of a file only transfers the changed blocks.
- **Integrity** — a block's key is a checksum of its contents; readers re-verify it.

**Per-user block scoping.** Block keys are namespaced by owner (`<owner>/<hash>`),
derived from the authenticated token — never from client input. It's what makes
client-driven direct uploads safe, trading cross-user dedup for two guarantees:

- **No cross-user side channel** — `/blocks/missing` can only answer "do *you*
  have this block?", so your upload speed can't reveal whether *another* user
  already holds one.
- **No cross-user poisoning** — the server mints a presigned PUT and never sees
  the bytes, so it can't check `sha256(data) == hash` on write. Namespacing the
  key means a bad block can only ever land in your own namespace.

> Chunking is **fixed-size** (like Dropbox). The `chunker.split()` seam is isolated
> so it can be swapped for content-defined chunking (rolling hash) without
> touching any other layer.

---

## Architecture

Hexagonal (ports & adapters) with dependency injection. Dependencies point
**inward**: the outer layers depend on the inner ones, never the reverse.

```
   client / browser
          │
          │ HTTP / WebSocket — JSON only: hashes, recipes, presigned urls
          ▼
   ┌──────────────────┐
   │  routers/        │  presentation
   └────────┬─────────┘
            │ Depends(...)
   ┌────────▼─────────┐     ┌───────────────────────┐
   │  application/    │ ──▶ │  domain/ + models/    │  pure core (no I/O)
   └────────┬─────────┘     └───────────────────────┘
            │ depends on ports
   ┌────────▼─────────┐
   │  ports/          │  abstract interfaces (ABCs)
   └────────▲─────────┘
            │ implemented by
   ┌────────┴─────────┐
   │  adapters/       │  infrastructure  ·  Mongo · Redis · B2
   └────────┬─────────┘
            │ has_block / presign  (metadata — never the bytes)
            ▼
   ┌──────────────────────────────┐
   │  B2   key = <owner>/<hash>   │ ◀╌╌╌╌ block bytes, presigned PUT / GET,
   └──────────────────────────────┘        client → B2, bypassing every layer above

   composition root: dependencies.py wires adapters → services
   cross-cutting:    auth_dependencies.py (bearer → user) · realtime.py (Notifier + ConnectionManager)
```

**Why this shape:**

- **No framework leakage** — the domain and application layers never import
  FastAPI, boto3, or pymongo.
- **Swappable infrastructure** — trade B2 for local disk, or Mongo for Postgres,
  by writing one new adapter and changing one line in `dependencies.py`. Nothing
  else moves.
- **Testable core** — services are unit-tested with in-memory fakes, no cloud
  required.

**Realtime path (pub/sub).** A commit/delete publishes onto a `ChangeBus`; every
server runs a subscribe-loop that fans out to *its own* WebSockets — so a change on
one server reaches a device connected to any other. The bus is a port: Redis in
production, in-process when `REDIS_URL` is unset.

```
   commit/delete ─▶ Notifier.notify(user) ─▶ ChangeBus.publish(user)
                                                    │  Redis pub/sub
                             ┌──────────────────────┴──────────────────────┐
                             ▼                                              ▼
                    Server A: listen-loop                         Server B: listen-loop
                             │                                              │
                    ConnectionManager.notify                     ConnectionManager.notify
                             │                                              │
                    Alice's sockets ✔                            (holds none) no-op
```

### Layers

| Layer | Directory | Knows about | Example |
|-------|-----------|-------------|---------|
| Presentation | `app/routers/` | HTTP, FastAPI | `files.py`, `auth.py`, `shares.py`, `link.py` |
| Application | `app/application/` | ports, domain | `FileService`, `AuthService`, `ShareService` |
| Domain | `app/domain/`, `app/models/` | nothing external | `security`, Pydantic models |
| Ports | `app/ports/` | — (abstract) | `BlockStore`, `FileRepository`, `UserRepository`, `ShareRepository`, `ShareLinkRepository`, `RefreshTokenRepository`, `ChangeBus` |
| Adapters | `app/adapters/` | B2, Mongo, Redis | `B2BlockStore`, `MongoFileRepository`, `MongoShareRepository`, `MongoShareLinkRepository`, `MongoRefreshTokenRepository`, `RedisChangeBus`, `InMemoryChangeBus` |

---

## Directory layout

```
app/
├── main.py                 # thin assembler: app + include_router + lifespan (Notifier)
├── config.py               # Settings (pydantic-settings, loads .env)
├── dependencies.py         # composition root; @lru_cache lazy singletons
├── auth_dependencies.py    # get_current_user (OAuth2 bearer → username)
├── realtime.py             # ConnectionManager (local WS registry) + Notifier (ChangeBus ↔ sockets)
│
├── routers/                # presentation — HTTP routes
│   ├── files.py            #   /files   list · commit · recipe · delete (share-aware)
│   ├── blocks.py           #   /blocks  missing · upload-urls · download-urls (share-aware)
│   ├── auth.py             #   /auth    register · login · refresh · logout
│   ├── shares.py           #   /shares  grant · revoke · incoming · outgoing · link (mint · revoke · list)
│   ├── link.py             #   /link    public token-only recipe · download-urls (no auth)
│   └── ws.py               #   /ws      WebSocket: push "changed" to a user's devices
│
├── application/            # use-case orchestrators (no framework deps)
│   ├── file_service.py     #   FileService: missing_blocks · upload_urls · commit_file · get_recipe · delete_file
│   ├── auth_service.py     #   AuthService: register · authenticate · refresh · logout
│   └── share_service.py    #   ShareService: share · revoke · list · can_read · create/revoke/list/resolve_link
│
├── domain/                 # pure logic, no I/O
│   └── security.py         #   bcrypt + JWT (access · refresh · share) encode/decode · new_jti
│
├── models/                 # Pydantic schemas (the "NoSQL schema")
│   ├── file.py             #   FileMeta → FileSummary / FileRecord
│   ├── user.py             #   User, RefreshToken, Token/AccessToken/Refresh req+resp
│   └── share.py            #   Share, ShareRequest, ShareLink, ShareLinkRequest
│
├── ports/                  # abstract interfaces (ABCs)
│   ├── block_store.py              #   BlockStore
│   ├── file_repository.py          #   FileRepository
│   ├── user_repository.py          #   UserRepository
│   ├── share_repository.py         #   ShareRepository
│   ├── share_link_repository.py    #   ShareLinkRepository
│   ├── refresh_token_repository.py #   RefreshTokenRepository (jti allowlist)
│   └── change_bus.py               #   ChangeBus (realtime pub/sub)
│
└── adapters/               # concrete implementations
    ├── b2_block_store.py                 # BlockStore             → Backblaze B2 (boto3)
    ├── mongo_file_repository.py          # FileRepository         → MongoDB
    ├── mongo_user_repository.py          # UserRepository         → MongoDB
    ├── mongo_share_repository.py         # ShareRepository        → MongoDB
    ├── mongo_share_link_repository.py    # ShareLinkRepository    → MongoDB
    ├── mongo_refresh_token_repository.py # RefreshTokenRepository → MongoDB
    ├── in_memory_change_bus.py           # ChangeBus              → in-process (default)
    └── redis_change_bus.py               # ChangeBus              → Redis pub/sub

client/                     # the sync client — imports nothing from app/
├── chunker.py              #   client-side chunking (block hash = shared contract)
├── api_client.py           #   httpx wrapper: negotiation calls + direct-to-B2 PUT/GET
├── state.py                #   LocalIndex: last-synced content hash per file
├── sync.py                 #   SyncEngine: delta push (local→server) / pull (server→local)
├── watcher.py              #   watchdog → auto-push on file change
├── ws_listener.py          #   WebSocket listener → pull on server "changed" push
└── __main__.py             #   CLI entry point (python -m client)

frontend/src/               # the web client — same delta engine, in the browser
├── main.tsx               #   theme (light/dark) + StrictMode root
├── App.tsx                #   session restore; public-link page vs logged-in app
├── auth.tsx               #   Login: register / log in
├── home.tsx               #   shell: header + "Your files" / "Shared with you" tabs
├── files.tsx              #   FileList: upload · download · delete · share panel
├── incoming.tsx           #   SharedWithMe: grants received, download by owner
├── shares.tsx             #   SharePanel: grant/revoke a user · mint/revoke links
├── public.tsx             #   PublicDownload: no-auth /?token=… page
│
└── lib/                   #   no JSX — everything that talks to the server
    ├── api.ts             #     typed fetch wrapper + token refresh on 401
    ├── crypto.ts          #     chunkFile + sha256Hex (Web Crypto)
    ├── download.ts        #     assembleBlocks (fetch · verify · reassemble) + saveBlob
    └── format.ts          #     displayPath · middleTruncate · formatSize · userColor

tests/                      # mirrors app/ + client/ ; 100% coverage gate
```

---

## Data models

Documents are schemaless in Mongo, so the schema lives in code as Pydantic models.
Adapters translate model ⇄ dict at the storage boundary (`.model_dump()` /
`Model(**doc)`); raw dicts never leak past the adapter.

A `├──` below means *inherits from*. The sharing models have no common base — each
is a standalone `BaseModel`, so they're listed flat, request body under the thing
it creates.

```
FileBase(owner, path, size, updated_at)
 ├── FileSummary                                     # listing view (no recipe)
 └── FileRecord(+ block_hashes)                      # full stored document

UserBase(username)
 ├── User(+ password_hash, created_at)               # internal — never returned by a route
 ├── UserRegisterRequest(+ password)                 # request body
 └── UserRegisterResponse(+ created_at)              # safe response (no hash)

Share(owner, path, shared_with, created_at)          # one user-to-user grant (Mongo `shares`)
ShareRequest(path, shared_with)                      #   → its grant/revoke request body

ShareLink(jti, owner, path, created_at, expires_at)  # one live public link (Mongo `share_links`)
ShareLinkRequest(path)                               #   → its mint request body
```

- **`FileSummary` vs `FileRecord`** — a deliberate read/write split: listings
  project away the (potentially huge) `block_hashes` array.
- **`Share`** — keyed on the `(owner, path, shared_with)` triple, one document
  per grant.
- **`ShareLink`** — keyed on `jti` (the token's unique id). Its *existence* is
  what makes a link live, so revoking is just deleting the row; `expires_at`
  mirrors the token's `exp` claim (both set once, at mint).

### Why NoSQL (MongoDB) over SQL

The access pattern drove this, not the data volume:

- **No joins to give up.** Every query in `app/adapters/` is a single-collection
  point lookup — `files` by `(owner, path)`, `share_links` by `jti`, `users` by
  `username`. Not one join, aggregation, or transaction in the codebase.
- **Recipes embed naturally.** `block_hashes` is an ordered array (~12,000 entries
  for a 50 GB file) stored inline in `FileRecord`, so a recipe read is one lookup.
  SQL wants a child `file_blocks` table, joined and re-sorted on every read.
- **Pydantic is already the schema.** `.model_dump()` / `Model(**doc)` at the adapter
  boundary *is* the whole ORM — no migrations, no second schema to keep in sync.
- **TTL indexes reap expiring rows for free** (`expires_at, expireAfterSeconds=0` on
  `refresh_tokens` and `share_links`) — no cron job. Postgres needs `pg_cron` or a
  sweeper.
- **Shard on `owner`** to scale out — a user's files and grants colocate (see
  [Scaling](#scaling)).

**The cost — referential integrity.** Nothing here *requires* NoSQL; Postgres would
serve this data fine.

- **What we gave up.** The cascade on delete is hand-rolled (`purge_for_file`) and
  non-atomic — an invariant the application layer must remember, not one the store
  enforces. Grant a share on a path that doesn't exist and it's silently accepted.
- **But `ON DELETE CASCADE` is only half a fix.** A foreign key on the *natural* key
  `(owner, path)` clears the rows, then happily resurrects them: delete
  `/report.pdf`, commit a new one at the same path, and the old grants reattach.
- **Identity is the bug; the database is a side issue.** The durable fix is an
  immutable surrogate `file_id` minted at first commit — which SQL gives you by
  convention, not by nature. See [Sharing tradeoffs](#sharing--permissions).

---

## API

All `/files` and `/blocks` routes require `Authorization: Bearer <token>`.
`owner` is always taken from the token, never from the request.

**Auth**

| Method | Path | Body | Returns |
|--------|------|------|---------|
| `POST` | `/auth/register` | JSON `{username, password}` | `201` `{username, created_at}` |
| `POST` | `/auth/login` | form `username, password` | `{access_token, token_type}` |

**Delta flow** (used by the sync client — file bytes go directly to/from B2)

| Method | Path | Body | Returns |
|--------|------|------|---------|
| `POST` | `/blocks/missing` | `{hashes: [...]}` | `{missing: [...]}` — which blocks the server needs |
| `POST` | `/blocks/upload-urls` | `{hashes: [...]}` | `{urls: {hash: presigned PUT url}}` |
| `POST` | `/blocks/download-urls?owner=&path=` | `{hashes: [...]}` | `{urls: {hash: presigned GET url}}` |
| `POST` | `/files/commit` | `{path, size, block_hashes}` | `201` `{path, size, blocks}` · `409` if blocks missing |
| `GET`  | `/files/recipe?path=…&owner=…` | — | `{path, size, block_hashes}` |
| `GET`  | `/files` | — | `{files: [FileSummary]}` |

On reads, `owner` is **optional** and defaults to the caller. Passing another
user's `owner` reads a file **shared with you** — the server gates it on a grant
and returns `404` (never `403`) if you have none.

**Sharing** (read-only grants; `owner` is always the caller's token identity)

| Method | Path | Body | Returns |
|--------|------|------|---------|
| `POST`   | `/shares` | `{path, shared_with}` | the `Share` — grant read on *your* file to a user |
| `DELETE` | `/shares` | `{path, shared_with}` | `204` — revoke a grant |
| `GET`    | `/shares/incoming` | — | `[Share]` — files shared **with me** |
| `GET`    | `/shares/outgoing` | — | `[Share]` — grants **I've made** |
| `POST`   | `/shares/link` | `{path}` | `{token}` — mint a public share-link token for *your* file |
| `DELETE` | `/shares/link/{jti}` | — | `204` — revoke a link by its `jti` (owner-scoped) |
| `GET`    | `/shares/link` | — | `[ShareLink]` — links **I've minted** that are still live |

**Public links** (no auth — the signed token *is* the identity)

| Method | Path | Body | Returns |
|--------|------|------|---------|
| `GET`  | `/link/recipe?token=…` | — | `{path, size, block_hashes}` — `404` on a bad/forged/**revoked/expired** token |
| `POST` | `/link/download-urls?token=…` | `{hashes: [...]}` | `{urls: {hash: presigned GET url}}` |

Interactive docs at `/docs` (Swagger UI, with the **Authorize** button).

### Request flow — delta upload (bytes never touch the app server)

```
1. client: blocks = chunker.split(data)            # hashes computed client-side
2. POST /blocks/missing {hashes}      → server: has_block(owner/h)? → missing[]
3. POST /blocks/upload-urls {missing} → server: presigned PUT url per owner/hash
4. client → PUT block bytes → B2 directly           (only the missing blocks)
5. POST /files/commit {path,size,hashes} → server verifies all present, saves FileRecord
```

### Request flow — delta download

```
1. GET /files/recipe?path=…          → server: FileRecord.block_hashes
2. POST /blocks/download-urls {h}    → server: presigned GET url per owner/hash
3. client → GET each block → B2 directly, re-verify sha256(block)==hash, reassemble
```

---

## Authentication

- **Passwords:** bcrypt with a per-password random salt. Only the hash is stored.
- **Tokens:** JWT (HS256), signed with `JWT_SECRET`, with an `exp` claim. The
  `sub` claim carries the username.
- **`get_current_user`** decodes the bearer token on each protected request and
  returns the username, or raises `401` for a missing / invalid / expired token.
- **No user enumeration:** unknown-username and wrong-password both return the
  same generic `401` on login.
- **No hash leakage:** routes return `UserRegisterResponse`, never the `User` model.

---

## Sharing & permissions

Read-only sharing comes in **two independent flavors**, but both rest on one
insight: **sharing never touches `FileService`.** It's a thin *authorization*
layer that only decides **which owner's namespace** a read resolves to. The
per-user block scoping does the rest — a recipient reads the owner's
`<owner>/<hash>` blocks but can never write into them, so "read-only" falls out
as *less code* (there is no `can_write`).

| | User-to-user | Public link |
|---|---|---|
| **Identity** | JWT auth token → `current_user` | signed share token → `(owner, path, jti)` |
| **Grant store** | Mongo `shares` collection | Mongo `share_links` — one row per **live** link, keyed on `jti` |
| **Authz check** | `ShareService.can_read` (you are the owner **or** a grant exists) | `ShareService.resolve_link` (valid signature, `typ == "share"`, **not expired**, **and its `jti` row still exists**) |
| **Mint** | `POST /shares` | `POST /shares/link` |
| **Read** | `GET /files/recipe?owner=`, `POST /blocks/download-urls?owner=` | `GET /link/recipe`, `POST /link/download-urls` (no login) |
| **Revoke** | `DELETE /shares` | `DELETE /shares/link/{jti}` (deletes the row) |
| **Expiry** | — (grants are durable) | `exp` claim, default 7 days (`SHARE_LINK_EXPIRE_MINUTES`) |

**Security invariants:**

- **`owner` on any mint/write comes from the token, never the body** — you can
  only share or link files you actually own.
- **`404`, never `403`, on denial** — refusing access never reveals that the
  file exists.
- **Auth and share tokens are non-interchangeable.** Both are HS256-signed with
  the same `JWT_SECRET`, so a `typ: "share"` claim (checked on decode) stops an
  auth token from being redeemed as a link, or vice-versa.
- **A share link carries no user.** The token *is* the capability: whoever holds
  `?token=…` may read exactly one `(owner, path)`, read-only, with no account.
- **Links expire and are revocable.** Two independent kill-switches, both checked
  on every read by `resolve_link`:
  - **Expiry** is free and offline — the `exp` claim is set once at mint (default
    7 days, `SHARE_LINK_EXPIRE_MINUTES`) and enforced by JWT decode, so an expired
    token fails signature-check before any DB lookup.
  - **Revocation** is an *allowlist*: minting writes a `share_links` row keyed on
    the token's `jti`, and a read only resolves while that row exists. `DELETE
    /shares/link/{jti}` deletes it — killing the link even though the signed token
    itself is still cryptographically valid. The same row powers `GET /shares/link`
    (list your live links). Revoke is **owner-scoped** (`{owner, jti}` filter), so
    no one can revoke a link they didn't mint.

**Revocation stops future reads, not bytes already in flight.**

- **What it kills.** `DELETE /shares` and `DELETE /shares/link/{jti}` take effect on
  the next `can_read` / `resolve_link`.
- **What it can't.** A presigned URL already handed out. B2 has never heard of the
  `shares` collection, so a recipient who fetched download URLs just before you
  revoked keeps them until those URLs expire.
- **How long.** `s3_url_ttl_seconds` (default **300**) bounds the window. It used to
  be an hour.
- **Why a window exists at all.** The same presigned direct-to-B2 transfer that keeps
  file bytes off the app server. The floor is set by the slowest legitimate download:
  `download_urls` signs a whole recipe at once and the client walks the blocks
  sequentially, so the TTL must outlast the entire transfer — at 4 MiB blocks and
  1 MB/s that's ~300 MB before the last URL goes stale. Minting URLs in batches as
  the client walks the recipe would decouple the two.

The `exp` claim and the row's `expires_at` are a **single source of truth** —
both computed once in `create_link`, so the JWT and the DB can never disagree.
A **TTL index** on `share_links.expires_at` reaps dead rows within about a minute
of expiry. It reclaims storage, not authority: `resolve_link` already rejects on
the `exp` claim, so the lagging row was inert before Mongo swept it.

**Tradeoffs (v1):**

- **Granting a nonexistent path** is silently accepted, creating a dangling grant
  that resolves to `404` on access.
- **Deleting a file purges its grants — but not atomically.** `DELETE /files` runs
  `purge_for_file` **before** `delete_file`. Purge-first fails safe: with no
  cross-collection transaction, a crash between the writes leaves a live file with
  no grants (recoverable), never a dead path with live grants (which would reattach
  on re-upload). `scripts/audit_storage.py --orphan-grants` reaps whatever the
  window leaves; closing it for good needs an immutable `file_id`.

---

## Sync client

A separate program (`client/`) that keeps a local folder in sync with the server —
the desktop-Dropbox piece. It talks **only** to the REST API and imports nothing
from `app/`, so a clean API is its entire contract. It does **delta sync**: it
chunks files itself and transfers only changed blocks, straight to/from B2.

```
file change      ──▶ watcher     ──▶ SyncEngine.push()   chunk → /blocks/missing → PUT missing → /files/commit
server "changed" ──▶ ws_listener ──▶ SyncEngine.pull()   /files/recipe → GET blocks (verify) → reassemble
```

- **`chunker`** splits files into hash-addressed blocks (its own copy of the 4 MiB
  scheme — the block hash is the shared contract with the server).
- **`LocalIndex`** remembers each file's last-synced content hash (persisted **outside**
  the synced folder), so `push` skips unchanged files without touching the network.
- **`push`** uploads only the blocks the server reports `missing`, then commits the recipe.
- **`pull`** downloads a differing file's blocks from B2, **re-verifies** each
  (`sha256(block) == hash`) before reassembling — so a corrupt/poisoned block can
  never silently corrupt a file.
- **`watcher`** (watchdog) fires `push()` on any file event.
- **`ws_listener`** holds a WebSocket to `/ws` and fires `pull()` on every server
  `"changed"` push — plus once on (re)connect, to reconcile anything missed while
  it was disconnected. It reconnects on its own every 3s if the socket drops.

**v1 limitations** (documented in `sync.py`):

- **No pull-side delta** — pull re-downloads a differing file's blocks in full,
  with no local block reuse. (It *does* skip files whose local blocks already
  match the recipe.)
- **Last-writer-wins** — no conflict copies.

---

## Configuration

All config comes from a `.env` file (see `.env.example`). Secrets are **required**
(no defaults) so the app refuses to start without them.

```
MONGODB_URI, MONGODB_DB
S3_ENDPOINT_URL, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY, S3_REGION, S3_BUCKET
S3_URL_TTL_SECONDS=300            # optional — presigned-URL lifetime; also the
                                  #   revocation window. Raise for slow, large downloads.
JWT_SECRET                        # required; generate: python -c "import secrets; print(secrets.token_urlsafe(48))"
JWT_ALGORITHM=HS256               # optional
ACCESS_TOKEN_EXPIRE_MINUTES=60    # optional
REFRESH_TOKEN_EXPIRE_MINUTES=10080 # optional (default 7 days) — refresh-token lifetime
SHARE_LINK_EXPIRE_MINUTES=10080   # optional (default 7 days) — public share-link lifetime
REDIS_URL                         # optional; set to enable multi-server realtime
                                  #   (Redis pub/sub). Unset = single-process in-memory bus.
```

> **macOS note:** MongoDB Atlas TLS requires `certifi` (`tlsCAFile=certifi.where()`),
> already wired in `dependencies.py`. The single `MongoClient` is shared by both
> repositories via a cached `_get_database()`.

---

## Running

### 1. Setup (once)

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then fill in real values (see Configuration)
```

### 2. Launch the server

```bash
uvicorn app.main:app --reload   # serves on http://127.0.0.1:8000
```

> **Multi-server (optional):** realtime works out of the box on one server via an
> in-process bus. To run multiple app servers, start Redis (`redis-server`) and
> set `REDIS_URL=redis://localhost:6379` — `notify` then fans out across servers
> via Redis pub/sub instead of staying local.

Open **http://127.0.0.1:8000/docs** for the interactive Swagger UI. Create an
account there (or via `curl`) before running the client:

```bash
curl -X POST http://127.0.0.1:8000/auth/register \
     -H "Content-Type: application/json" \
     -d '{"username": "alice", "password": "secret123"}'
```

### 3. Launch the sync client

With the server running and the venv active, point the client at a local folder:

```bash
python -m client \
    --server   http://127.0.0.1:8000 \
    --username alice --password secret123 \
    --folder   ~/DropboxClone
```

The client logs in, does an initial two-way sync, then **watches the folder** and
pushes changes as they happen — while a WebSocket to `/ws` pulls remote updates
the moment another device commits. Drop a file into `~/DropboxClone` and it uploads;
run a second client against a different folder (or machine) with the same account
and it appears there, without polling.

```bash
# one-shot sync instead of continuous watching:
python -m client --server http://127.0.0.1:8000 \
    --username alice --password secret123 --folder ~/DropboxClone --once
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--server` | `http://127.0.0.1:8000` | server base URL |
| `--username` / `--password` | *(required)* | account to log in as (must already exist) |
| `--folder` | *(required)* | local folder to sync |
| `--once` | off | sync once and exit (no watching) |

### 4. Launch the web UI (optional)

A React + Vite single-page app in `frontend/` gives you a browser client with
the same delta engine as the Python client — chunking, dedup, and hash
verification all run in the browser, and block bytes go **browser → B2 directly**
via presigned URLs. It covers:

- **Auth** — register / login / logout (JWT held in memory).
- **Your files** — list, upload (block-level dedup), download (on-read hash
  verify), delete.
- **Shared with you** — a second tab: incoming grants (`/shares/incoming`), with
  hash-verified download from the owner's `<owner>/<hash>` namespace.
- **Sharing** — an expandable per-file panel: grant read-only access to another
  user, see **who the file is currently shared with** (`/shares/outgoing`) and
  revoke any of them, plus mint / copy / revoke public share-links.
- **Public links** — a no-auth `/?token=…` page that resolves a share-link and
  downloads the file (hash-verified) with no account.
- **Real-time** — both tabs hold a WebSocket (`/ws`). "Your files" refreshes when
  the same account commits or deletes elsewhere; "Shared with you" refreshes when
  someone grants, revokes, or deletes a file shared with you. A **commit** notifies
  only the owner — a recipient's list shows grants, not file contents, so a new
  version changes nothing they can see.

> The download path — fetch each block, re-verify `sha256(block) == hash`,
> reassemble — lives once in `frontend/src/lib/download.ts` (`assembleBlocks`), shared
> by all three of the owned-file, shared-file, and public-link flows.

```bash
cd frontend
npm install                     # once
npm run dev                     # serves on http://localhost:5173
```

Keep the API server (step 2) running in another terminal. Vite proxies the API
routes (`/auth`, `/files`, `/blocks`, `/shares`, `/link`, `/ws`) to
`http://127.0.0.1:8000`, so there's no CORS setup for local dev. Open
**http://localhost:5173** and register or log in.

> Because the browser PUTs/GETs block bytes straight to B2, the bucket needs a
> CORS rule allowing your dev origin (`http://localhost:5173`) for `GET`, `PUT`,
> and `HEAD`. Add your production origin to that rule when you deploy.

| Script | What it does |
|--------|--------------|
| `npm run dev` | dev server with hot-reload on `:5173` |
| `npm run build` | type-check (`tsc`) then bundle to `frontend/dist/` |
| `npm run preview` | serve the production build locally |

## Demo: the whole system via `curl`

With the server running (and `jq` installed), this walks through upload →
share → read-as-another-user → public link → revoke-link → revoke-grant. It
uses a small single-block file, so the block hash is just `sha256(file)`.

```bash
BASE=http://127.0.0.1:8000

# 1. Two accounts
curl -s -X POST $BASE/auth/register -H 'Content-Type: application/json' \
     -d '{"username":"alice","password":"secret123"}'
curl -s -X POST $BASE/auth/register -H 'Content-Type: application/json' \
     -d '{"username":"bob","password":"secret123"}'

# 2. Log in (form-encoded, per OAuth2) and capture bearer tokens
ALICE=$(curl -s -X POST $BASE/auth/login \
     -d 'username=alice&password=secret123' | jq -r .access_token)
BOB=$(curl -s -X POST $BASE/auth/login \
     -d 'username=bob&password=secret123'   | jq -r .access_token)

# 3. Bob uploads a small (single-block) file via the delta flow
echo "hello shared world" > /tmp/demo.txt
HASH=$(shasum -a 256 /tmp/demo.txt | cut -d' ' -f1)
SIZE=$(wc -c < /tmp/demo.txt | tr -d ' ')

#   a) which blocks does the server still need?
curl -s -X POST $BASE/blocks/missing -H "Authorization: Bearer $BOB" \
     -H 'Content-Type: application/json' -d "{\"hashes\":[\"$HASH\"]}"
#   b) get a presigned PUT url and push the bytes straight to B2
PUT=$(curl -s -X POST $BASE/blocks/upload-urls -H "Authorization: Bearer $BOB" \
     -H 'Content-Type: application/json' -d "{\"hashes\":[\"$HASH\"]}" \
     | jq -r ".urls[\"$HASH\"]")
curl -s -X PUT "$PUT" --data-binary @/tmp/demo.txt
#   c) commit the recipe
curl -s -X POST $BASE/files/commit -H "Authorization: Bearer $BOB" \
     -H 'Content-Type: application/json' \
     -d "{\"path\":\"/demo.txt\",\"size\":$SIZE,\"block_hashes\":[\"$HASH\"]}"

# 4. Bob shares /demo.txt with Alice
curl -s -X POST $BASE/shares -H "Authorization: Bearer $BOB" \
     -H 'Content-Type: application/json' \
     -d '{"path":"/demo.txt","shared_with":"alice"}'

# 5. Alice reads Bob's file: recipe -> presigned GET -> bytes
curl -s "$BASE/files/recipe?owner=bob&path=/demo.txt" -H "Authorization: Bearer $ALICE"
GET=$(curl -s -X POST "$BASE/blocks/download-urls?owner=bob&path=/demo.txt" \
     -H "Authorization: Bearer $ALICE" -H 'Content-Type: application/json' \
     -d "{\"hashes\":[\"$HASH\"]}" | jq -r ".urls[\"$HASH\"]")
curl -s "$GET"                                   # -> hello shared world

# 6. Public share link — redeemable with NO auth header
TOKEN=$(curl -s -X POST $BASE/shares/link -H "Authorization: Bearer $BOB" \
     -H 'Content-Type: application/json' -d '{"path":"/demo.txt"}' | jq -r .token)
curl -s "$BASE/link/recipe?token=$TOKEN"          # -> the recipe, no login

# 7. Bob lists his live links, then revokes this one by its jti
JTI=$(curl -s "$BASE/shares/link" -H "Authorization: Bearer $BOB" | jq -r '.[0].jti')
curl -s -X DELETE "$BASE/shares/link/$JTI" -H "Authorization: Bearer $BOB"
#   the SAME token is still cryptographically valid, yet its row is gone -> revoked
curl -s -o /dev/null -w '%{http_code}\n' "$BASE/link/recipe?token=$TOKEN"   # -> 404

# 8. Revoke Alice's grant — she now gets 404 on the shared file too
curl -s -X DELETE $BASE/shares -H "Authorization: Bearer $BOB" \
     -H 'Content-Type: application/json' \
     -d '{"path":"/demo.txt","shared_with":"alice"}'
curl -s -o /dev/null -w '%{http_code}\n' \
     "$BASE/files/recipe?owner=bob&path=/demo.txt" -H "Authorization: Bearer $ALICE"  # -> 404
```

> Files over 4 MiB span multiple blocks — the real client (`python -m client`)
> handles chunking, per-block negotiation, and reassembly for you.

## Testing

```bash
pip install -r requirements-dev.txt
pytest                          # runs with coverage; fails under 90%
```

Tests mirror the `app/` and `client/` trees. External services (B2, Mongo) and
HTTP are mocked or faked, so the suite runs offline and deterministically.

---

## Scaling

A note on what it would take to run this for **large files** and **many users**.
The short version: the *data plane* already scales, because content addressing +
presigned direct-to-B2 transfer means **file bytes never touch the app server**.
The work is almost all in the *control plane*.

### Large files

Two things are already right:

- **Bytes bypass the app server** — block data goes browser/client → B2 directly;
  the API only moves tiny JSON.
- **Identical blocks transfer once** — dedup, within a user's namespace.

What starts to hurt:

- **Unbounded fan-out.** A 50 GB file is ~12,000 blocks — today that's one giant
  `upload-urls` response and (in the web client) 12,000 concurrent `PUT`s. Bound
  the in-flight concurrency to a small pool (~6–10) and mint presigned URLs in
  **batches** as the pool drains, rather than all at once.
- **No resumability.** A dropped connection restarts the transfer. Content
  addressing softens this (already-committed blocks are skipped by
  `/blocks/missing`), but large blocks want **S3 multipart upload**, and the
  client wants to **checkpoint** progress.
- **Fixed-size chunking defeats dedup on edits.** Inserting one byte at the front
  shifts every 4 MiB boundary, so every block hash changes. **Content-defined
  chunking** (rolling hash, à la restic/borg) is the fix — the `chunker.split()`
  seam is already isolated for exactly this swap.
- **Whole-file reassembly in memory.** The download path collects every block into
  one `Blob`/buffer — a huge file OOMs the tab or process. **Stream** to disk as
  blocks arrive (File System Access API / a `ReadableStream`) instead.

### Many users

Here the bottlenecks move to the app tier, Mongo, and the real-time layer:

- **Cross-server realtime fan-out — done.** This *was* the first thing to break
  on horizontal scale: `realtime.ConnectionManager` holds sockets in-process, so a
  commit on instance A couldn't notify a socket on instance B. It's now solved by
  the **`ChangeBus`** — `notify` publishes to Redis pub/sub and every server fans
  out `{"type":"changed"}` to its own sockets (see the Architecture "Realtime
  path"). Sticky WebSocket sessions are no longer needed. Falls back to an
  in-process bus when `REDIS_URL` is unset. What's left here is *tuning*, not
  architecture: per-user channels instead of one global channel if publish volume
  ever gets hot.
- **The app tier is nearly stateless already.** Auth is a stateless JWT and bytes
  bypass the app, so FastAPI instances scale horizontally behind a load balancer
  with autoscaling — and with the pub/sub bus shipped, that's now fully true.
- **Mongo indexing & sharding.** Every hot query is indexed — `files` on
  `(owner, path)` unique; `shares` on `(owner, path, shared_with)` unique (whose
  leftmost prefix also serves the `(owner, path)` purge) plus `shared_with` alone
  for the recipient's list; `share_links` on `jti` unique, `(owner, path)`, and a
  TTL on `expires_at`. At very large scale, **shard on `owner`** so a user's files
  and blocks colocate.
- **CDN in front of B2.** Cache public-link downloads at the edge instead of
  re-fetching per request; presigned GETs work behind a CDN.
- **Garbage collection that scales.** Now that file delete ships, orphaned blocks
  are real. The one-shot full-scan audit (`scripts/audit_storage.py` — phantom
  files, orphaned blocks, orphaned grants) is fine at this size but won't scale —
  the endgame is **per-block reference counting** or an incremental mark-and-sweep,
  not a full bucket + collection scan.

The highest-leverage step — the **Redis pub/sub bus** behind `ConnectionManager`,
which unlocks running more than one server at all — is **done**. With the app tier
now horizontally scalable, the next control-plane investments are **Mongo indexing
& sharding** and **reference-counted GC**, both of which matter only as data
volume grows.

---

## Status & roadmap

**Done:**
- **Core storage** — content-addressed blocks, chunking/dedup, REST API, JWT auth,
  ports & adapters throughout.
- **Delta sync** — client-side chunking, have/need negotiation, presigned
  direct-to-B2 transfer, per-user block scoping, re-verify-on-read.
- **Sync client** — folder watcher, push/pull, WebSocket-driven pull.
- **Real-time** — `ChangeBus` over Redis pub/sub, so a commit on one server reaches
  a device on another. Each route notifies exactly the users whose view changed.
- **Sharing** — user-to-user grants and public share-links, both revocable, links
  also expiring. Authorization never touches storage. Revocation closes the read
  window in 5 minutes (`s3_url_ttl_seconds`), bounded below by download speed.
- **File deletion** — owner-scoped, cascades to grants and links before the recipe.
- **Refresh tokens** — `jti` allowlist with TTL reap; `typ`-guarded against
  cross-use; the web session survives reload and auto-refreshes on a 401.
- **Web UI** — React + Vite: tabbed "Your files" / "Shared with you", upload,
  hash-verified download, delete, full sharing, no-auth public download page.
- **Indexes** — unique on `username`, `jti`, `(owner, path)`, and the grant triple;
  TTL reap on expiring `refresh_tokens` and `share_links`.
- **100% backend coverage**, plus frontend unit tests.

**Next:**
- Pull-side delta (reuse local blocks instead of re-downloading a changed file).
- Content-defined chunking (so delta survives insertions).
- Streaming chunking for very large files (avoid reading whole file into memory).
- Orphaned-block garbage collection — now unlocked, since delete is the first
  operation that creates real orphans. `scripts/audit_storage.py` is the cleanup
  path (it already reaps orphaned grants too); a scheduled mark-and-sweep GC
  finally has a use case.

**Hardening backlog:**
- File versioning (conflict copies).
- Refresh-token rotation (currently non-rotating).
- httpOnly-cookie token storage (currently `localStorage`).
