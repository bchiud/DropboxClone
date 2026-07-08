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
derived from the authenticated token — never from client input. This trades
cross-user dedup for security: no cross-user side channel (your upload speed
can't reveal whether *another* user has a block) and no cross-user poisoning (you
can only write under your own namespace). It's what makes client-driven direct
uploads safe.

> Chunking is **fixed-size** (like Dropbox). The `chunker.split()` seam is isolated
> so it can be swapped for content-defined chunking (rolling hash) without
> touching any other layer.

---

## Architecture

Hexagonal (ports & adapters) with dependency injection. Dependencies point
**inward**: the outer layers depend on the inner ones, never the reverse.

```
                 ┌─────────────────────────────────────────┐
   HTTP  ───────▶│  routers/         (FastAPI APIRouters)   │  presentation
                 └───────────────────┬─────────────────────┘
                                     │ Depends(...)
                 ┌───────────────────▼─────────────────────┐
                 │  application/     (FileService,          │  use cases /
                 │                    AuthService)          │  orchestration
                 └───────┬───────────────────────┬─────────┘
                         │ depends on ports        │ uses
             ┌───────────▼─────────┐   ┌───────────▼─────────┐
             │  ports/  (abstract  │   │  domain/  (chunker, │  pure core
             │  interfaces)        │   │  security) + models/│  (no I/O)
             └───────────▲─────────┘   └─────────────────────┘
                         │ implemented by
             ┌───────────┴─────────────────────────────────┐
             │  adapters/  (B2BlockStore, MongoFileRepo,    │  infrastructure
             │              MongoUserRepo)                  │
             └─────────────────────────────────────────────┘

   dependencies.py  = composition root (wires adapters → services)
   auth_dependencies.py = get_current_user (bearer token → username)
```

**Why this shape:** the domain and application layers never import FastAPI, boto3,
or pymongo. You could swap B2 for local disk, or Mongo for Postgres, by writing one
new adapter and changing one line in `dependencies.py` — nothing else moves. The
services are unit-tested with in-memory fakes, no cloud required.

### Layers

| Layer | Directory | Knows about | Example |
|-------|-----------|-------------|---------|
| Presentation | `app/routers/` | HTTP, FastAPI | `files.py`, `auth.py` |
| Application | `app/application/` | ports, domain | `FileService`, `AuthService` |
| Domain | `app/domain/`, `app/models/` | nothing external | `chunker`, `security`, Pydantic models |
| Ports | `app/ports/` | — (abstract) | `BlockStore`, `FileRepository`, `UserRepository` |
| Adapters | `app/adapters/` | B2, Mongo | `B2BlockStore`, `MongoFileRepository` |

---

## Directory layout

```
app/
├── main.py                 # thin assembler: create app + include_router
├── config.py               # Settings (pydantic-settings, loads .env)
├── dependencies.py         # composition root; @lru_cache lazy singletons
├── auth_dependencies.py    # get_current_user (OAuth2 bearer → username)
│
├── routers/                # presentation — HTTP routes
│   ├── files.py            #   /files  list · commit · recipe (+ legacy upload/download)
│   ├── blocks.py           #   /blocks  missing · upload-urls · download-urls
│   └── auth.py             #   /auth   register · login
│
├── application/            # use-case orchestrators (no framework deps)
│   ├── file_service.py     #   FileService: save/load + missing_blocks/upload_urls/commit_file/get_recipe
│   └── auth_service.py     #   AuthService: register / authenticate
│
├── domain/                 # pure logic, no I/O
│   ├── chunker.py          #   split bytes → (hash, block) pairs
│   └── security.py         #   bcrypt hashing + JWT encode/decode
│
├── models/                 # Pydantic schemas (the "NoSQL schema")
│   ├── file.py             #   FileMeta → FileSummary / FileRecord
│   └── user.py             #   User, UserRegisterRequest/Response, TokenResponse
│
├── ports/                  # abstract interfaces (ABCs)
│   ├── block_store.py      #   BlockStore
│   ├── file_repository.py  #   FileRepository
│   └── user_repository.py  #   UserRepository
│
└── adapters/               # concrete implementations
    ├── b2_block_store.py         # BlockStore  → Backblaze B2 (boto3)
    ├── mongo_file_repository.py  # FileRepository → MongoDB
    └── mongo_user_repository.py  # UserRepository → MongoDB

client/                     # the sync client — imports nothing from app/
├── chunker.py              #   client-side chunking (block hash = shared contract)
├── api_client.py           #   httpx wrapper: negotiation calls + direct-to-B2 PUT/GET
├── state.py                #   LocalIndex: last-synced content hash per file
├── sync.py                 #   SyncEngine: delta push (local→server) / pull (server→local)
├── watcher.py              #   watchdog → auto-push on file change
└── __main__.py             #   CLI entry point (python -m client)

tests/                      # mirrors app/ + client/ ; 100% coverage gate
```

---

## Data models

Documents are schemaless in Mongo, so the schema lives in code as Pydantic models.
Adapters translate model ⇄ dict at the storage boundary (`.model_dump()` /
`Model(**doc)`); raw dicts never leak past the adapter.

```
FileMeta(owner, path, size, updated_at)
 ├── FileSummary               # listing view (no recipe)
 └── FileRecord(+ block_hashes)  # full stored document

UserBase(username)
 ├── User(+ password_hash, created_at)     # internal — never returned by a route
 ├── UserRegisterRequest(+ password)       # request body
 └── UserRegisterResponse(+ created_at)    # safe response (no hash)
```

`FileSummary` vs `FileRecord` is a deliberate read/write split: listings project
away the (potentially huge) `block_hashes` array.

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
| `POST` | `/blocks/download-urls` | `{hashes: [...]}` | `{urls: {hash: presigned GET url}}` |
| `POST` | `/files/commit` | `{path, size, block_hashes}` | `201` `{path, size, blocks}` · `409` if blocks missing |
| `GET`  | `/files/recipe?path=…` | — | `{path, size, block_hashes}` |
| `GET`  | `/files` | — | `{files: [FileSummary]}` |

**Legacy whole-file flow** (server proxies the bytes — see "Retiring the legacy API")

| Method | Path | Body | Returns |
|--------|------|------|---------|
| `POST` | `/files?path=…` | multipart `file` | `{path, size, blocks}` |
| `GET`  | `/files/content?path=…` | — | raw bytes |

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

## Retiring the legacy API

The whole-file endpoints (`POST /files`, `GET /files/content`) predate delta sync.
They proxy file bytes through the app server and buffer the whole file in memory —
superseded by the delta flow. Nothing but ad-hoc `curl` uses them now (the sync
client is delta-only).

Because this is a single codebase with one client you fully control, a clean
**removal** is appropriate — the multi-release *deprecation* dance is for public
APIs with external consumers you can't coordinate with. Suggested order:

1. **Confirm no callers** — `grep` for `/files/content`, `POST /files` (multipart),
   `save_file`, `load_file` across `client/` and tests.
2. **Remove the routes** — `upload` + `download` in `routers/files.py`.
3. **Remove the service methods** — `FileService.save_file` / `load_file`.
4. **Drop the now-unused server chunker** — `app/domain/chunker.py` (only
   `save_file`/`load_file` used it; the client has its own copy). Delete its tests.
5. **Update tests** — remove the legacy route/service tests; the delta tests remain.
6. **Update this README** — delete the "Legacy whole-file flow" table + this section.

Keep them instead if you want a no-client "upload via `curl`/Swagger" path — but
then buffer-in-memory and server-bandwidth costs are the price.

---

## Sync client

A separate program (`client/`) that keeps a local folder in sync with the server —
the desktop-Dropbox piece. It talks **only** to the REST API and imports nothing
from `app/`, so a clean API is its entire contract. It does **delta sync**: it
chunks files itself and transfers only changed blocks, straight to/from B2.

```
file change  ──▶ watcher ──▶ SyncEngine.push()   chunk → /blocks/missing → PUT missing → /files/commit
every N secs ──────────────▶ SyncEngine.pull()   /files/recipe → GET blocks (verify) → reassemble
```

- **`chunker`** splits files into hash-addressed blocks (its own copy of the 4 MiB
  scheme — the block hash is the shared contract with the server).
- **`LocalIndex`** remembers each file's last-synced content hash (persisted **outside**
  the synced folder), so `push` skips unchanged files without touching the network.
- **`push`** uploads only the blocks the server reports `missing`, then commits the recipe.
- **`pull`** downloads a differing file's blocks from B2, **re-verifies** each
  (`sha256(block) == hash`) before reassembling — so a corrupt/poisoned block can
  never silently corrupt a file.
- **`watcher`** (watchdog) fires `push()` on any file event; a timer drives `pull()`.

**v1 limitations (documented in `sync.py`):** pull re-downloads a differing file's
blocks in full (no local block reuse), periodic pull (not real-time), last-writer-wins
(no conflict copies).

---

## Configuration

All config comes from a `.env` file (see `.env.example`). Secrets are **required**
(no defaults) so the app refuses to start without them.

```
MONGODB_URI, MONGODB_DB
S3_ENDPOINT_URL, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY, S3_REGION, S3_BUCKET
JWT_SECRET                        # required; generate: python -c "import secrets; print(secrets.token_urlsafe(48))"
JWT_ALGORITHM=HS256               # optional
ACCESS_TOKEN_EXPIRE_MINUTES=60    # optional
BLOCK_SIZE=4194304                # optional (4 MiB)
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
pushes changes as they happen, pulling remote updates every `--poll` seconds
(default 10). Drop a file into `~/DropboxClone` and it uploads; run a second client
against a different folder (or machine) with the same account and it appears there.

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
| `--poll` | `10` | seconds between remote-change pulls |

## Testing

```bash
pip install -r requirements-dev.txt
pytest                          # runs with coverage; fails under 90%
```

Tests mirror the `app/` and `client/` trees. External services (B2, Mongo) and
HTTP are mocked or faked, so the suite runs offline and deterministically.

---

## Status & roadmap

**Done:** content-addressed storage, chunking/dedup, REST API, JWT auth, full
ports/adapters architecture, sync client (folder watcher + push/pull),
**delta sync** (client-side chunking + have/need negotiation + presigned
direct-to-B2 transfer + per-user block scoping + re-verify-on-read),
100% test coverage.

**Next:**
- Real-time change notifications (WebSocket) — instant pulls instead of polling.
- Sharing & permissions.
- Web UI.
- Streaming chunking for very large files (avoid reading whole file into memory).

**Hardening backlog:** unique index on `username`, file delete + orphaned-block
garbage collection, file versioning (conflict copies), refresh tokens,
content-defined chunking.
```
