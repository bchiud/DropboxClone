"""Unit tests for the filesystem watcher."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from client import watcher
from client.watcher import PushOnChangeHandler


def file_event():
    return SimpleNamespace(is_directory=False)


def dir_event():
    return SimpleNamespace(is_directory=True)


def test_file_event_triggers_push():
    engine = MagicMock()
    PushOnChangeHandler(engine).on_any_event(file_event())
    engine.push.assert_called_once()


def test_directory_event_is_ignored():
    engine = MagicMock()
    PushOnChangeHandler(engine).on_any_event(dir_event())
    engine.push.assert_not_called()


def test_watch_schedules_and_starts_observer(tmp_path):
    engine = MagicMock()
    with patch("client.watcher.Observer") as MockObserver:
        observer = MagicMock()
        MockObserver.return_value = observer
        result = watcher.watch(engine, tmp_path)

    observer.schedule.assert_called_once()
    observer.start.assert_called_once()
    assert result is observer
