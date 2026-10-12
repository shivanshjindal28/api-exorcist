"""
Saving an uploaded project folder to disk, safely.

The browser sends each file with its path inside the chosen folder, and that
path is whatever the client says it is. A crafted upload naming
`../../.ssh/authorized_keys` or `C:\\Windows\\...` must not be able to write
outside the scan's own temporary directory (the "zip slip" class of bug), so
every name is rebuilt from its parts here and anything that could escape is
refused. Nothing that is saved is ever executed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

MAX_FILES = 20_000
MAX_TOTAL_BYTES = 200 * 1024 * 1024

_DRIVE = re.compile(r"^[A-Za-z]:")


class UploadRejected(ValueError):
    """The upload as a whole cannot be accepted; the message says why."""


def safe_relative(name: str) -> PurePosixPath | None:
    """The upload's path as a safe relative path, or None to skip the file."""
    # A folder picker always sends a relative path. An absolute one is not
    # something a browser produces, so it is refused rather than reinterpreted.
    if not name or "\x00" in name or name.startswith(("/", "\\")):
        return None
    parts = [p for p in name.replace("\\", "/").split("/") if p not in ("", ".")]
    if not parts or _DRIVE.match(parts[0]):
        return None
    if any(p == ".." or p.startswith("~") or ":" in p for p in parts):
        return None
    return PurePosixPath(*parts)


@dataclass
class SavedUpload:
    root: Path
    name: str
    files: int = 0
    bytes: int = 0
    skipped: list[str] = field(default_factory=list)


def strip_common_root(paths: list[PurePosixPath]) -> tuple[str, list[PurePosixPath]]:
    """A folder picker sends `project/src/app.py`; scan from inside `project/`."""
    firsts = {p.parts[0] for p in paths if len(p.parts) > 1}
    if len(firsts) == 1 and all(len(p.parts) > 1 for p in paths):
        top = next(iter(firsts))
        return top, [PurePosixPath(*p.parts[1:]) for p in paths]
    return "", paths


def save_files(dest: Path, files: list[tuple[str, bytes]]) -> SavedUpload:
    """Write `(name, content)` pairs under `dest`, refusing unsafe names."""
    if not files:
        raise UploadRejected("the upload contained no files")
    if len(files) > MAX_FILES:
        raise UploadRejected(
            f"{len(files)} files is more than the {MAX_FILES} accepted. Leave out "
            "dependency folders such as node_modules, which the scanner never reads"
        )
    total = sum(len(c) for _, c in files)
    if total > MAX_TOTAL_BYTES:
        raise UploadRejected(
            f"{total // (1024 * 1024)} MB is more than the "
            f"{MAX_TOTAL_BYTES // (1024 * 1024)} MB accepted"
        )

    safe: list[tuple[PurePosixPath, bytes]] = []
    skipped: list[str] = []
    for name, content in files:
        rel = safe_relative(name)
        if rel is None:
            skipped.append(name[:120])
            continue
        safe.append((rel, content))
    if not safe:
        raise UploadRejected("no file in the upload had a usable name")

    top, rels = strip_common_root([r for r, _ in safe])
    saved = SavedUpload(root=dest, name=top or "uploaded folder", skipped=skipped)
    root = dest.resolve()
    for rel, (_, content) in zip(rels, safe, strict=True):
        target = (root / Path(*rel.parts)).resolve()
        # Belt and braces: even a name that passed the checks above must land
        # inside the destination after resolution.
        if root not in target.parents:
            saved.skipped.append(str(rel)[:120])
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        saved.files += 1
        saved.bytes += len(content)
    return saved
