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
| Presentation | `app/routers/` | HTTP, FastAPI | `files.py`, `auth.py`, `shares.py`, `link.py` |
| Application | `app/application/` | ports, domain | `FileService`, `AuthService`, `ShareService` |
| Domain | `app/domain/`, `app/models/` | nothing external | `chunker`, `security`, Pydantic models |
| Ports | `app/ports/` | — (abstract) | `BlockStore`, `FileRepository`, `UserRepository`, `ShareRepository` |
| Adapters | `app/adapters/` | B2, Mongo | `B2BlockStore`, `MongoFileRepository`, `MongoShareRepository` |

---

## Directory layout

```
app/
├── main.py                 # thin assembler: create app + include_router
├── config.py               # Settings (pydantic-settings, loads .env)
├── dependencies.py         # composition root; @lru_cache lazy singletons
├── auth_dependencies.py    # get_current_user (OAuth2 bearer → username)
│
├── realtime.py             # ConnectionManager: in-memory WebSocket registry per user
│
├── routers/                # presentation — HTTP routes
│   ├── files.py            #   /files   list · commit · recipe (share-aware)
│   ├── blocks.py           #   /blocks  missing · upload-urls · download-urls (share-aware)
│   ├── auth.py             #   /auth    register · login
│   ├── shares.py           #   /shares  grant · revoke · incoming · outgoing · link
│   ├── link.py             #   /link    public token-only recipe · download-urls (no auth)
│   └── ws.py               #   /ws      WebSocket: push "changed" to a user's devices
│
├── application/            # use-case orchestrators (no framework deps)
│   ├── file_service.py     #   FileService: list · missing_blocks · upload_urls · commit_file · get_recipe
│   ├── auth_service.py     #   AuthService: register / authenticate
│   └── share_service.py    #   ShareService: share · revoke · list · can_read (authorization)
│
├── domain/                 # pure logic, no I/O
│   └── security.py         #   bcrypt hashing + JWT (access + share-link) encode/decode
│
├── models/                 # Pydantic schemas (the "NoSQL schema")
│   ├── file.py             #   FileMeta → FileSummary / FileRecord
│   ├── user.py             #   User, UserRegisterRequest/Response, TokenResponse
│   └── share.py            #   Share, ShareRequest, ShareLinkRequest
│
├── ports/                  # abstract interfaces (ABCs)
│   ├── block_store.py      #   BlockStore
│   ├── file_repository.py  #   FileRepository
│   ├── user_repository.py  #   UserRepository
│   └── share_repository.py #   ShareRepository
│
└── adapters/               # concrete implementations
    ├── b2_block_store.py         # BlockStore     → Backblaze B2 (boto3)
    ├── mongo_file_repository.py  # FileRepository  → MongoDB
    ├── mongo_user_repository.py  # UserRepository  → MongoDB
    └── mongo_share_repository.py # ShareRepository → MongoDB

client/                     # the sync client — imports nothing from app/
├── chunker.py              #   client-side chunking (block hash = shared contract)
├── api_client.py           #   httpx wrapper: negotiation calls + direct-to-B2 PUT/GET
├── state.py                #   LocalIndex: last-synced content hash per file
├── sync.py                 #   SyncEngine: delta push (local→server) / pull (server→local)
├── watcher.py              #   watchdog → auto-push on file change
├── ws_listener.py          #   WebSocket listener → pull on server "changed" push
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

Share(owner, path, shared_with, created_at)   # one user-to-user grant (Mongo `shares`)
 ├── ShareRequest(path, shared_with)           # grant/revoke request body
 └── ShareLinkRequest(path)                     # mint-a-public-link request body
```

`FileSummary` vs `FileRecord` is a deliberate read/write split: listings project
away the (potentially huge) `block_hashes` array. A `Share` is keyed on the
`(owner, path, shared_with)` triple — one document per grant.

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

**Public links** (no auth — the signed token *is* the identity)

| Method | Path | Body | Returns |
|--------|------|------|---------|
| `GET`  | `/link/recipe?token=…` | — | `{path, size, block_hashes}` — `404` on a bad/forged token |
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
| **Identity** | JWT auth token → `current_user` | signed share token → `(owner, path)` |
| **Grant store** | Mongo `shares` collection | none — stateless; the token *is* the grant |
| **Authz check** | `ShareService.can_read` (you are the owner **or** a grant exists) | `decode_share_token` (valid signature **and** `typ == "share"`) |
| **Mint** | `POST /shares` | `POST /shares/link` |
| **Read** | `GET /files/recipe?owner=`, `POST /blocks/download-urls?owner=` | `GET /link/recipe`, `POST /link/download-urls` (no login) |
| **Revoke** | `DELETE /shares` | — (links are permanent; see below) |

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

**Tradeoffs (v1):** public links **don't expire and can't be revoked** short of
rotating `JWT_SECRET` (add an `exp` claim, or a per-link id checked in Mongo, to
change that). Granting a path that doesn't exist just creates a harmless dangling
grant that resolves to `404` on access.

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

## Demo: the whole system via `curl`

With the server running (and `jq` installed), this walks through upload →
share → read-as-another-user → public link → revoke. It uses a small
single-block file, so the block hash is just `sha256(file)`.

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
curl -s "$BASE/link/recipe?token=$TOKEN"

# 7. Revoke Alice's grant — she now gets 404 (the link still works)
curl -s -X DELETE $BASE/shares -H "Authorization: Bearer $BOB" \
     -H 'Content-Type: application/json' \
     -d '{"path":"/demo.txt","shared_with":"alice"}'
curl -s -o /dev/null -w '%{http_code}\n' \
     "$BASE/files/recipe?owner=bob&path=/demo.txt" -H "Authorization: Bearer $ALICE"
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

## Status & roadmap

**Done:** content-addressed storage, chunking/dedup, REST API, JWT auth, full
ports/adapters architecture, sync client (folder watcher + push/pull),
delta sync (client-side chunking + have/need negotiation + presigned
direct-to-B2 transfer + per-user block scoping + re-verify-on-read),
**real-time sync** (WebSocket push: commit notifies the owner's devices, which
pull instantly instead of polling),
**sharing & permissions** (read-only user-to-user grants + stateless public
share-links, both gated by an authorization layer that never touches storage),
100% test coverage.

**Next:**
- Web UI.
- Pull-side delta (reuse local blocks instead of re-downloading a changed file).
- Content-defined chunking (so delta survives insertions).
- Streaming chunking for very large files (avoid reading whole file into memory).
- Multi-server scaling: Redis pub/sub behind the WebSocket ConnectionManager.

**Hardening backlog:** unique index on `username`, file delete + orphaned-block
garbage collection, file versioning (conflict copies), refresh tokens,
content-defined chunking.
```
