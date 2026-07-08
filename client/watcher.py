"""Filesystem watcher: push local changes to the server as they happen.

The event handler (pure logic) is separated from the observer wiring so the
handler can be unit-tested without a real filesystem watch.
"""
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from client.sync import SyncEngine


class PushOnChangeHandler(FileSystemEventHandler):
    def __init__(self, engine: SyncEngine):
        self._engine = engine

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return  # directory events carry no file content to push
        # push() rescans and uploads only what changed, so redundant events
        # are cheap and safe (a debounce is a future optimization).
        self._engine.push()


def watch(engine: SyncEngine, folder: Path) -> Observer:
    observer = Observer()
    observer.schedule(PushOnChangeHandler(engine), str(folder), recursive=True)
    observer.start()
    return observer
