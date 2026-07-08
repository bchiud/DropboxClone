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
   blocks:  key=hash → bytes             ← stored in B2
```

This buys three things for free:

- **Deduplication** — identical blocks (across files or users) are stored once.
- **Delta sync** — editing part of a file only re-uploads the changed blocks.
- **Integrity** — a block's key is a checksum of its contents.

> Chunking is currently **fixed-size** (like Dropbox). The `chunker.split()` seam
> is isolated so it can be swapped for content-defined chunking (rolling hash)
> later without touching any other layer.

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
│   ├── files.py            #   /files  upload · list · download
│   └── auth.py             #   /auth   register · login
│
├── application/            # use-case orchestrators (no framework deps)
│   ├── file_service.py     #   FileService: save_file / load_file / list_files
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
├── api_client.py           #   httpx wrapper over the server REST API
├── state.py                #   LocalIndex: last-synced content hash per file
├── sync.py                 #   SyncEngine: push (local→server) / pull (server→local)
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

All `/files` routes require `Authorization: Bearer <token>`.

| Method | Path | Body | Returns |
|--------|------|------|---------|
| `POST` | `/auth/register` | JSON `{username, password}` | `201` `{username, created_at}` |
| `POST` | `/auth/login` | form `username, password` | `{access_token, token_type}` |
| `POST` | `/files?path=…` | multipart `file` | `{path, size, blocks}` |
| `GET`  | `/files` | — | `{files: [FileSummary]}` |
| `GET`  | `/files/content?path=…` | — | raw bytes |

Interactive docs at `/docs` (Swagger UI, with the **Authorize** button).

### Request flow — upload

```
POST /files ─▶ files.router ─▶ FileService.save_file(owner, path, data)
                                  │
                                  ├─ chunker.split(data) → [(hash, block)…]
                                  ├─ BlockStore.put_block(hash, block)  ×N   (dedup: skips existing)
                                  └─ FileRepository.save(FileRecord)          (recipe → Mongo)
```

### Request flow — download

```
GET /files/content ─▶ FileService.load_file(owner, path)
                        ├─ FileRepository.get(owner, path) → FileRecord
                        └─ BlockStore.get_block(h) for h in record.block_hashes → reassemble
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

## Sync client

A separate program (`client/`) that keeps a local folder in sync with the server —
the desktop-Dropbox piece. It talks **only** to the REST API and imports nothing
from `app/`, so a clean API is its entire contract.

```
file change  ──▶ watcher ──▶ SyncEngine.push() ──▶ upload changed files
every N secs ──────────────▶ SyncEngine.pull() ──▶ download remote changes
```

- **`LocalIndex`** remembers each file's last-synced content hash (persisted to a
  JSON file **outside** the synced folder), so `push`/`pull` only transfer what
  actually changed — not the whole folder every scan.
- **`push`** walks the folder and uploads files whose content hash differs from the
  index; **`pull`** downloads server files that are missing or differ locally.
- **`watcher`** (watchdog) fires `push()` on any file event; a timer drives `pull()`.

**v1 limitations (documented in `sync.py`):** whole-file transfer (no network-level
delta yet — the server still dedups *storage*), periodic pull (not real-time),
last-writer-wins (no conflict copies).

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
ports/adapters architecture, **sync client** (folder watcher + push/pull),
100% test coverage.

**Next:**
- Delta sync — block-level endpoints + client-side chunking so only changed
  *blocks* cross the network (the content-addressed design's big payoff).
- Real-time change notifications (WebSocket) — instant pulls instead of polling.
- Sharing & permissions.
- Web UI.

**Hardening backlog:** unique index on `username`, file delete + orphaned-block
garbage collection, file versioning (conflict copies), refresh tokens,
content-defined chunking.
```
