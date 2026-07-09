"""One-shot storage audit for the Dropbox clone.

Cross-checks the Mongo ``files`` recipes against the B2 block objects in both
directions:

* **phantom files**   – a file recipe references a block that is missing from B2
  (the file can no longer be fully downloaded).
* **orphaned blocks** – a B2 object under ``<owner>/<hash>`` that no surviving
  file recipe references (pure wasted storage).

The block key layout is ``<owner>/<hash>`` (see ``FileService._block_key``), and
the only thing that references blocks is the ``files`` collection, so reading all
of it yields a complete reference set — nothing else can legitimately point at a
block.

Dry-run by default: it only reports. Pass ``--delete`` to remove phantom file
docs and/or orphaned block objects (you are asked to confirm unless ``--yes``).

Usage (from the repo root, venv active)::

    python -m scripts.audit_storage                  # report both directions
    python -m scripts.audit_storage --phantom-files  # only files -> blocks
    python -m scripts.audit_storage --orphan-blocks  # only blocks -> files
    python -m scripts.audit_storage --delete         # act (with confirmation)

Caveat: don't run ``--delete --orphan-blocks`` during an active upload — blocks
that were just PUT but not yet committed would look orphaned and get swept.
"""

from __future__ import annotations

import argparse

import boto3
import certifi
from pymongo import MongoClient

from app.config import settings


def _make_clients():
    s3 = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region,
    )
    db = MongoClient(host=settings.mongodb_uri, tlsCAFile=certifi.where())[
        settings.mongodb_db
    ]
    return s3, db


def _bucket_objects(s3, bucket: str) -> dict[str, int]:
    """Every object key in the bucket -> its size in bytes."""
    objects: dict[str, int] = {}
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            objects[obj["Key"]] = obj["Size"]
    return objects


def _referenced_keys(files: list[dict]) -> set[str]:
    refs: set[str] = set()
    for doc in files:
        owner = doc["owner"]
        for block_hash in doc.get("block_hashes", []):
            refs.add(f"{owner}/{block_hash}")
    return refs


def _human(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TiB"  # unreachable, keeps type checkers happy


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit B2 blocks against Mongo file recipes (both directions)."
    )
    parser.add_argument(
        "--delete", action="store_true",
        help="actually delete phantom docs / orphaned blocks (default: report only)",
    )
    parser.add_argument(
        "--yes", action="store_true",
        help="skip the confirmation prompt when deleting",
    )
    parser.add_argument(
        "--phantom-files", action="store_true",
        help="only the files -> blocks direction",
    )
    parser.add_argument(
        "--orphan-blocks", action="store_true",
        help="only the blocks -> files direction",
    )
    args = parser.parse_args()

    # neither flag => both directions; one flag => only that direction
    do_phantom = args.phantom_files or not args.orphan_blocks
    do_orphan = args.orphan_blocks or not args.phantom_files

    s3, db = _make_clients()
    files = list(
        db["files"].find({}, {"owner": 1, "path": 1, "block_hashes": 1, "_id": 0})
    )
    objects = _bucket_objects(s3, settings.s3_bucket)
    refs = _referenced_keys(files)

    print(
        f"files: {len(files)}  |  "
        f"bucket objects: {len(objects)}  |  "
        f"referenced keys: {len(refs)}\n"
    )

    phantom_files: list[tuple[dict, list[str]]] = []
    if do_phantom:
        for doc in files:
            owner = doc["owner"]
            missing = [
                h for h in doc.get("block_hashes", [])
                if f"{owner}/{h}" not in objects
            ]
            if missing:
                phantom_files.append((doc, missing))
        print(
            f"== phantom files (recipe references a block missing from B2): "
            f"{len(phantom_files)} =="
        )
        for doc, missing in phantom_files:
            total = len(doc.get("block_hashes", []))
            print(f"  {doc['owner']} {doc['path']}  "
                  f"({len(missing)}/{total} blocks missing)")
        print()

    orphan_keys: list[str] = []
    if do_orphan:
        orphan_keys = sorted(k for k in objects if k not in refs)
        reclaim = sum(objects[k] for k in orphan_keys)
        print(
            f"== orphaned blocks (B2 object no recipe references): "
            f"{len(orphan_keys)}  ({_human(reclaim)} reclaimable) =="
        )
        for k in orphan_keys:
            print(f"  {k}  ({_human(objects[k])})")
        print()

    if not args.delete:
        print("dry run — nothing deleted. Re-run with --delete to act.")
        return

    if not (phantom_files or orphan_keys):
        print("nothing to delete.")
        return

    if not args.yes:
        answer = input(
            f"Delete {len(phantom_files)} file docs and "
            f"{len(orphan_keys)} block objects? type 'yes' to confirm: "
        )
        if answer.strip().lower() != "yes":
            print("aborted.")
            return

    for doc, _missing in phantom_files:
        db["files"].delete_one({"owner": doc["owner"], "path": doc["path"]})
    if phantom_files:
        print(f"deleted {len(phantom_files)} phantom file docs.")

    for key in orphan_keys:
        s3.delete_object(Bucket=settings.s3_bucket, Key=key)
    if orphan_keys:
        print(f"deleted {len(orphan_keys)} orphaned block objects.")


if __name__ == "__main__":
    main()
