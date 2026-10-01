"""SyncEngine regression tests: unpushed local edits must survive a pull, and deletions must sync.

Both gaps were reproduced in review (2026-09-30):
- pull() overwrote a file whose local edit hadn't been pushed yet, because it only compared local content to the
  server's recipe, never to the last-synced content in LocalIndex. The edit was lost with no 412 and no conflict copy.
- deletions never synced: push() only walks files that exist on disk, so a local delete never reached the server,
  and the next pull() downloaded the file again. A server-side delete never removed the local copy either.

The assertions describe outcomes, not a mechanism: an unpushed edit may survive in place or in a conflict copy, and
a delete may be detected however the engine likes (e.g. via LocalIndex.known_paths()). The one contract they assume
is that ApiClient gains delete_file(path), mirrored by FakeApi.delete_file.
"""
from pathlib import Path

from client.state import LocalIndex
from client.sync import SyncEngine
from tests.client.test_sync import FakeApi


def _device(tmp_path: Path, api: FakeApi, name: str) -> tuple[SyncEngine, Path]:
    # each device gets its own folder and its own LocalIndex (kept outside the folder, as in the real client)
    folder = tmp_path / name
    folder.mkdir()
    return SyncEngine(api, LocalIndex(tmp_path / f"{name}.index.json"), folder), folder


def _contents(folder: Path) -> list[bytes]:
    return [f.read_bytes() for f in folder.rglob("*") if f.is_file()]


# --- unpushed local edits vs. pull ---

def test_pull_does_not_lose_an_unpushed_local_edit(tmp_path):
    api = FakeApi()
    laptop, laptop_folder = _device(tmp_path, api, "laptop")
    phone, phone_folder = _device(tmp_path, api, "phone")
    (laptop_folder / "a.txt").write_bytes(b"v1")
    laptop.push()
    phone.pull()

    (phone_folder / "a.txt").write_bytes(b"phone edit")  # edited, but the phone's watcher hasn't pushed yet
    (laptop_folder / "a.txt").write_bytes(b"laptop edit")
    laptop.push()  # the laptop's edit reaches the server first

    phone.pull()  # the server's "changed" notification arrives on the phone

    # the phone's edit may survive in place or as a conflict copy, but it must not be silently overwritten
    assert b"phone edit" in _contents(phone_folder)


def test_pull_still_updates_a_file_with_no_local_edits(tmp_path):
    # guard against over-correcting the fix above: an untouched local copy must still take the server's version
    api = FakeApi()
    laptop, laptop_folder = _device(tmp_path, api, "laptop")
    phone, phone_folder = _device(tmp_path, api, "phone")
    (laptop_folder / "a.txt").write_bytes(b"v1")
    laptop.push()
    phone.pull()

    (laptop_folder / "a.txt").write_bytes(b"v2")
    laptop.push()
    phone.pull()

    assert (phone_folder / "a.txt").read_bytes() == b"v2"


# --- deletions ---

def test_a_local_delete_reaches_the_server(tmp_path):
    api = FakeApi()
    laptop, folder = _device(tmp_path, api, "laptop")
    (folder / "a.txt").write_bytes(b"v1")
    laptop.push()

    (folder / "a.txt").unlink()
    laptop.push()

    assert "/a.txt" not in api.recipes


def test_a_locally_deleted_file_is_not_downloaded_again(tmp_path):
    api = FakeApi()
    laptop, folder = _device(tmp_path, api, "laptop")
    (folder / "a.txt").write_bytes(b"v1")
    laptop.push()

    (folder / "a.txt").unlink()
    laptop.sync()  # push then pull, as the client does on startup

    assert not (folder / "a.txt").exists()


def test_a_server_side_delete_removes_the_local_copy(tmp_path):
    api = FakeApi()
    laptop, laptop_folder = _device(tmp_path, api, "laptop")
    phone, phone_folder = _device(tmp_path, api, "phone")
    (laptop_folder / "a.txt").write_bytes(b"v1")
    laptop.push()
    phone.pull()

    api.delete_file("/a.txt")  # deleted from another device or the web UI
    phone.pull()

    assert not (phone_folder / "a.txt").exists()


def test_a_server_side_delete_keeps_a_local_copy_with_unpushed_edits(tmp_path):
    # deleting a file someone is still editing would lose their work; the local edit must survive
    api = FakeApi()
    laptop, laptop_folder = _device(tmp_path, api, "laptop")
    phone, phone_folder = _device(tmp_path, api, "phone")
    (laptop_folder / "a.txt").write_bytes(b"v1")
    laptop.push()
    phone.pull()

    (phone_folder / "a.txt").write_bytes(b"phone edit")  # not pushed yet
    api.delete_file("/a.txt")
    phone.pull()

    assert b"phone edit" in _contents(phone_folder)


# --- conflict copies (how pull keeps both sides of a conflict) ---

def _conflict(tmp_path: Path) -> tuple[FakeApi, SyncEngine, Path]:
    """Phone and laptop both edit a.txt after syncing v1; the laptop's edit reaches the server first."""
    api = FakeApi()
    laptop, laptop_folder = _device(tmp_path, api, "laptop")
    phone, phone_folder = _device(tmp_path, api, "phone")
    (laptop_folder / "a.txt").write_bytes(b"v1")
    laptop.push()
    phone.pull()
    (phone_folder / "a.txt").write_bytes(b"phone edit")
    (laptop_folder / "a.txt").write_bytes(b"laptop edit")
    laptop.push()
    return api, phone, phone_folder


def test_a_conflict_keeps_the_servers_version_as_a_conflict_copy(tmp_path):
    _, phone, folder = _conflict(tmp_path)

    pulled = phone.pull()

    assert (folder / "a.txt").read_bytes() == b"phone edit"
    assert (folder / "a (conflicted copy).txt").read_bytes() == b"laptop edit"
    assert pulled == ["/a (conflicted copy).txt"]


def test_repeated_pulls_during_a_conflict_do_not_duplicate_the_copy(tmp_path):
    _, phone, folder = _conflict(tmp_path)

    phone.pull()
    phone.pull()  # e.g. another "changed" notification before the phone's push runs

    assert sorted(f.name for f in folder.iterdir()) == ["a (conflicted copy).txt", "a.txt"]


def test_a_conflict_copy_never_overwrites_an_existing_copy_with_other_content(tmp_path):
    _, phone, folder = _conflict(tmp_path)
    (folder / "a (conflicted copy).txt").write_bytes(b"an older conflict")

    phone.pull()

    assert (folder / "a (conflicted copy).txt").read_bytes() == b"an older conflict"
    assert (folder / "a (conflicted copy 2).txt").read_bytes() == b"laptop edit"


def test_a_conflict_copy_reaches_the_server_on_the_next_push(tmp_path):
    api, phone, _ = _conflict(tmp_path)
    phone.pull()

    phone.push()

    # the server now holds both edits: a.txt (the phone's, via push's last-writer-wins reconcile) and the copy
    assert api.blocks[api.recipes["/a (conflicted copy).txt"]["block_hashes"][0]] == b"laptop edit"
    assert api.blocks[api.recipes["/a.txt"]["block_hashes"][0]] == b"phone edit"


def test_pull_leaves_an_unpushed_edit_alone_when_the_server_is_unchanged(tmp_path):
    api = FakeApi()
    laptop, folder = _device(tmp_path, api, "laptop")
    (folder / "a.txt").write_bytes(b"v1")
    laptop.push()
    (folder / "a.txt").write_bytes(b"local edit")  # only this side changed: no conflict, just not pushed yet

    assert laptop.pull() == []
    assert sorted(f.name for f in folder.iterdir()) == ["a.txt"]
    assert (folder / "a.txt").read_bytes() == b"local edit"


def test_a_push_conflict_keeps_the_other_devices_edit_as_a_conflict_copy(tmp_path):
    # the other order: the phone pushes BEFORE it pulls, so the conflict surfaces as a 412 in push, not in pull
    api, phone, folder = _conflict(tmp_path)

    phone.push()  # 412 (the laptop's edit is on the server) -> reconcile -> the phone's bytes win the path
    phone.push()  # the watcher fires again for the new copy

    assert (folder / "a (conflicted copy).txt").read_bytes() == b"laptop edit"
    assert api.blocks[api.recipes["/a.txt"]["block_hashes"][0]] == b"phone edit"
    assert api.blocks[api.recipes["/a (conflicted copy).txt"]["block_hashes"][0]] == b"laptop edit"


# --- a local delete that push() hasn't sent yet (watch mode: a pull can run before the watcher's push) ---

def test_pull_does_not_redownload_a_local_delete_push_hasnt_sent(tmp_path):
    api = FakeApi()
    laptop, folder = _device(tmp_path, api, "laptop")
    (folder / "a.txt").write_bytes(b"v1")
    laptop.push()

    (folder / "a.txt").unlink()
    laptop.pull()  # a "changed" notification for another file arrives before the watcher's push
    assert not (folder / "a.txt").exists()

    laptop.push()  # ...and the delete still goes out
    assert "/a.txt" not in api.recipes


def test_a_remote_edit_wins_over_a_local_delete_push_hasnt_sent(tmp_path):
    api = FakeApi()
    laptop, laptop_folder = _device(tmp_path, api, "laptop")
    phone, phone_folder = _device(tmp_path, api, "phone")
    (laptop_folder / "a.txt").write_bytes(b"v1")
    laptop.push()
    phone.pull()

    (phone_folder / "a.txt").unlink()  # the phone deletes it, but hasn't pushed the delete
    (laptop_folder / "a.txt").write_bytes(b"laptop edit")
    laptop.push()  # meanwhile the laptop edits it

    phone.pull()
    phone.push()

    # deleting a file that someone else just changed would lose their edit, so the edit wins
    assert (phone_folder / "a.txt").read_bytes() == b"laptop edit"
    assert api.blocks[api.recipes["/a.txt"]["block_hashes"][0]] == b"laptop edit"
