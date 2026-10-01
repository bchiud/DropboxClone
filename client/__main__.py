"""Sync client entry point.

Usage:
    python -m client --username U --password P --folder ~/Dropbox [--server URL] [--once]
"""
import argparse
import asyncio
from pathlib import Path

from client.api_client import ApiClient
from client.state import LocalIndex
from client.sync import SyncEngine
from client.watcher import watch
from client.ws_listener import listen


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
    args = parser.parse_args(argv)

    engine, api = build_engine(args.server, args.username, args.password, args.folder)
    print(f"initial sync: {engine.sync()}")

    if args.once:
        api.close()
        return

    # push on local changes (watchdog thread) + pull on server notifications (WebSocket)
    observer = watch(engine, args.folder)
    print(f"watching {args.folder} + real-time listening — Ctrl-C to stop")
    try:
        asyncio.run(listen(args.server, api, engine))
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()
        api.close()


if __name__ == "__main__":
    main()
