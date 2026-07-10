import unicodedata
from typing import Annotated

from pydantic import AfterValidator


# A path is a file's identity — repositories match on the exact string — so it
# needs one canonical spelling, or "foo.txt" and "/foo.txt" become two records
# for one file. The leading "/" roots it in the owner's namespace, which the
# sync client relies on when it emits nested paths like "/docs/notes.txt".
# NFC is normalized rather than rejected: macOS reports filenames as NFD and
# browsers as NFC, and that difference is not the client's fault.
def _must_be_rooted(v: str) -> str:
    v = unicodedata.normalize("NFC", v)
    if not v.startswith("/"):
        raise ValueError("path must start with '/'")
    if "\\" in v:
        raise ValueError("path must not contain '\\'")
    if "\0" in v:
        raise ValueError("path must not contain a NUL ('\\0') character")
    segments = v.split("/")[1:]
    if not segments or (any(s in ("", ".", "..") for s in segments)):
        raise ValueError(f"invalid path segment in {v!r}")
    return v


RootedPath = Annotated[str, AfterValidator(_must_be_rooted)]
