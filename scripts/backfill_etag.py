"""One-shot backfill for the optimistic-concurrency + block-index migration.

Two schema additions landed without a data migration, so **existing** documents
predate them and break on read/write:

* **files.etag** – `FileSummary`/`FileRecord` now require `etag = sha256(recipe)`.
  A pre-existing `files` doc has no `etag`, so `FileSummary(**doc)` raises a
  Pydantic validation error and `GET /files` 500s ("could not load files"). The
  etag is deterministic from `block_hashes`, so this recomputes and stores it.
  Required, not cosmetic: the commit CAS filters on the stored `etag`, so without
  it an old file can never be updated (perpetual 412) either.

* **blocks (owner, hash)** – the block index is a cache of what's in B2. It starts
  empty and self-heals (an unindexed block is reported "missing" → the client
  re-uploads idempotently → commit re-indexes it), so this is **optional** — pass
  ``--blocks`` to pre-seed it and skip that initial re-upload wave. It reads every
  recipe's `(owner, hash)` pairs; because the index is meant to be a subset of B2,
  only run it when B2 actually holds those blocks (i.e. not mid-migration-loss).

Dry-run by default: it only reports counts. Pass ``--apply`` to write (you're
asked to confirm unless ``--yes``). Both writes are idempotent — the etag pass
only touches docs missing the field, the block pass upserts.

Usage (from the repo root, venv active)::

    python -m scripts.backfill_etag                 # report only (etags)
    python -m scripts.backfill_etag --apply         # write missing etags
    python -m scripts.backfill_etag --blocks        # also report block-index gap
    python -m scripts.backfill_etag --blocks --apply --yes   # write both, no prompt
"""

from __future__ import annotations

import argparse

import certifi
from pymongo import MongoClient, UpdateOne

from app.config import settings
from app.domain.recipe import recipe_etag


def _db():
    return MongoClient(host=settings.mongodb_uri, tlsCAFile=certifi.where())[
        settings.mongodb_db
    ]


def _etag_backfill(db, apply: bool) -> int:
    """Set etag on every files doc that lacks one. Returns how many were stale."""
    stale = list(
        db["files"].find({"etag": {"$exists": False}}, {"_id": 1, "block_hashes": 1})
    )
    print(f"== files missing etag: {len(stale)} ==")
    if apply and stale:
        for doc in stale:
            db["files"].update_one(
                {"_id": doc["_id"]},
                {"$set": {"etag": recipe_etag(doc["block_hashes"])}},
            )
        print(f"  set etag on {len(stale)} file docs.")
    return len(stale)


def _block_index_backfill(db, apply: bool) -> int:
    """Upsert (owner, hash) for every referenced block not already indexed.

    Returns how many rows are missing from the index.
    """
    referenced = {
        (doc["owner"], h)
        for doc in db["files"].find({}, {"owner": 1, "block_hashes": 1, "_id": 0})
        for h in doc.get("block_hashes", [])
    }
    indexed = {
        (d["owner"], d["hash"])
        for d in db["blocks"].find({}, {"owner": 1, "hash": 1, "_id": 0})
    }
    missing = referenced - indexed
    print(
        f"== block index: {len(referenced)} referenced, "
        f"{len(indexed)} indexed, {len(missing)} to add =="
    )
    if apply and missing:
        db["blocks"].bulk_write(
            [
                UpdateOne(
                    {"owner": o, "hash": h},
                    {"$setOnInsert": {"owner": o, "hash": h}},
                    upsert=True,
                )
                for (o, h) in missing
            ],
            ordered=False,
        )
        print(f"  upserted {len(missing)} block-index rows.")
    return len(missing)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill files.etag (and optionally the block index) for "
        "documents that predate those fields."
    )
    parser.add_argument(
        "--blocks", action="store_true",
        help="also backfill the (owner, hash) block index (optional; it self-heals)",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="actually write (default: report only)",
    )
    parser.add_argument(
        "--yes", action="store_true",
        help="skip the confirmation prompt when applying",
    )
    args = parser.parse_args()

    db = _db()
    stale_etags = _etag_backfill(db, apply=False)
    missing_blocks = _block_index_backfill(db, apply=False) if args.blocks else 0

    if not args.apply:
        print("\ndry run — nothing written. Re-run with --apply to act.")
        return

    if not (stale_etags or missing_blocks):
        print("\nnothing to backfill.")
        return

    if not args.yes:
        answer = input(
            f"\nSet etag on {stale_etags} file docs"
            + (f" and index {missing_blocks} blocks" if args.blocks else "")
            + "? type 'yes' to confirm: "
        )
        if answer.strip().lower() != "yes":
            print("aborted.")
            return

    print()
    _etag_backfill(db, apply=True)
    if args.blocks:
        _block_index_backfill(db, apply=True)


if __name__ == "__main__":
    main()
