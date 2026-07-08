"""Sync client entry point.

Usage:
    python -m client --username U --password P --folder ~/Dropbox [--server URL] [--once]
"""
import argparse
import time
from pathlib import Path

from client.api_client import ApiClient
from client.state import LocalIndex
from client.sync import SyncEngine
from client.watcher import watch


def build_engine(base_url: str, username: str, password: str, folder: Path) -> tuple[SyncEngine, ApiClient]:
    folder.mkdir(parents=True, exist_ok=True)
    api = ApiClient(base_url)
    api.login(username, password)
    index_path = folder.parent / (folder.name + ".index.json")  # kept outside the synced folder
    return SyncEngine(api, LocalIndex(index_path), folder), api


def main(argv=None):
    parser = argparse.ArgumentParser(prog="client")
    parser.add_argument("--server", default="http://127.0.0.1:8000")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--folder", required=True, type=Path)
    parser.add_argument("--once", action="store_true", help="sync once and exit")
    parser.add_argument("--poll", type=float, default=10.0, help="pull interval seconds")
    args = parser.parse_args(argv)

    engine, api = build_engine(args.server, args.username, args.password, args.folder)
    print(f"initial sync: {engine.sync()}")

    if args.once:
        api.close()
        return

    observer = watch(engine, args.folder)
    print(f"watching {args.folder} — Ctrl-C to stop")
    try:
        while True:
            time.sleep(args.poll)
            pulled = engine.pull()
            if pulled:
                print(f"pulled: {pulled}")
    except KeyboardInterrupt:
        observer.stop()
        observer.join()
        api.close()


if __name__ == "__main__":
    main()
