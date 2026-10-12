"""
Append-only, hash-chained audit log for Safe Kill decisions.

Why hash-chained
----------------
A removal decision in a bank has to survive an audit months later. A plain log
file proves nothing: anyone with write access can edit a line to say an
endpoint was approved by someone who never saw it, and the file looks the same
afterwards. Here every entry carries the SHA-256 of its own canonical content
together with the hash of the entry before it. Editing, deleting or reordering
any entry breaks every hash after it, and `verify` reports the first entry at
which the chain stops holding.

What this does and does not guarantee
-------------------------------------
It makes tampering *detectable*, not impossible. Someone who can rewrite the
whole file can recompute the whole chain. The standard answer, and the
deployment intention, is to anchor the latest hash somewhere the operator does
not control (a WORM bucket, the bank's SIEM, a signed daily digest). The chain
is what makes that one small anchor sufficient to vouch for every entry before
it. Stated plainly so nobody reads more into "hash-chained" than it delivers.

Concurrent writers
------------------
The CLI, the API server, and any second replica may share one file. Each append
takes an exclusive lock on a sidecar `<log>.lock`, re-reads the head under it,
writes, and fsyncs before releasing. Without the lock two processes read the
same head and both link to it, which forks the chain; a test with four writer
processes reproduced that on the unlocked code. The lock is advisory (flock on
POSIX, a byte-range lock on Windows), so it binds every writer that goes through
this class and nothing else. A shared network filesystem whose locking cannot
be trusted is not a supported store; a deployment there wants one writer.

Every transition is written, not only terminal ones. The design requires that
Blocked, Rejected and Denied are recorded with the same rigour as Retired,
because "why was this endpoint *not* removed" is as much an audit question as
the reverse; writing the full path also records *how* each state was reached.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any

GENESIS = "0" * 64
LOCK_TIMEOUT_S = 30.0


class AuditLockTimeout(RuntimeError):
    """Another writer held the audit lock too long. The decision is not written."""


def _try_lock(fh: IO[bytes]) -> bool:
    try:
        if sys.platform == "win32":
            import msvcrt
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _unlock(fh: IO[bytes]) -> None:
    if sys.platform == "win32":
        import msvcrt
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def exclusive(path: Path, timeout: float = LOCK_TIMEOUT_S) -> Iterator[None]:
    """Hold the log's sidecar lock. Fails loudly rather than writing unlocked."""
    lock_path = path.with_name(path.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as fh:
        deadline = time.monotonic() + timeout
        while not _try_lock(fh):
            if time.monotonic() > deadline:
                raise AuditLockTimeout(
                    f"could not lock {lock_path} within {timeout:.0f}s; "
                    "another writer is holding it"
                )
            time.sleep(0.005)
        try:
            yield
        finally:
            _unlock(fh)


def _canonical(payload: dict[str, Any]) -> bytes:
    """One byte representation per entry, independent of dict ordering."""
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(payload)).hexdigest()


@dataclass(frozen=True)
class AuditEntry:
    seq: int
    at: str                     # ISO timestamp on the controller's clock
    endpoint_id: str
    from_state: str | None
    to_state: str
    reason: str
    actor: str                  # "safekill-controller", or a named approver
    evidence: dict[str, Any]
    prev_hash: str
    hash: str

    def body(self) -> dict[str, Any]:
        """Everything the hash covers: all fields except the hash itself."""
        return {
            "seq": self.seq,
            "at": self.at,
            "endpoint_id": self.endpoint_id,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "reason": self.reason,
            "actor": self.actor,
            "evidence": self.evidence,
            "prev_hash": self.prev_hash,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.body(), "hash": self.hash}


@dataclass(frozen=True)
class ChainCheck:
    ok: bool
    entries: int
    broken_at: int | None = None
    problem: str = ""


@dataclass
class AuditLog:
    """In memory by default; mirrored to a JSON Lines file when given a path."""

    path: Path | None = None
    entries: list[AuditEntry] = field(default_factory=list)
    _seen_size: int = field(default=-1, init=False, repr=False)

    def __post_init__(self) -> None:
        self._sync()

    def _sync(self) -> None:
        """Reload from disk if another process has appended since we last read.

        The CLI and the REST API share one log file. Without this, each loads
        the file once and links its next entry to the head *it* last saw; the
        moment the other process has appended in between, the chain breaks
        on the very next entry. Checking the file size is enough because the
        file only ever grows.

        Writers appending at the same instant are serialised by `exclusive`;
        reads take the same lock so they never see a half-written last line.
        """
        if self.path is None or not self.path.exists():
            return
        with exclusive(self.path):
            self._reload()

    def _reload(self) -> None:
        """The unlocked part of `_sync`; the caller holds the lock."""
        assert self.path is not None
        if not self.path.exists():
            return
        size = self.path.stat().st_size
        if size != self._seen_size:
            self.entries = load(self.path)
            self._seen_size = size

    @property
    def head(self) -> str:
        self._sync()
        return self.entries[-1].hash if self.entries else GENESIS

    def append(
        self,
        *,
        at: str,
        endpoint_id: str,
        from_state: str | None,
        to_state: str,
        reason: str,
        actor: str,
        evidence: dict[str, Any] | None = None,
    ) -> AuditEntry:
        if self.path is None:
            return self._append(at, endpoint_id, from_state, to_state, reason,
                                actor, evidence)
        with exclusive(self.path):
            self._reload()
            return self._append(at, endpoint_id, from_state, to_state, reason,
                                actor, evidence)

    def _append(
        self,
        at: str,
        endpoint_id: str,
        from_state: str | None,
        to_state: str,
        reason: str,
        actor: str,
        evidence: dict[str, Any] | None,
    ) -> AuditEntry:
        body: dict[str, Any] = {
            "seq": len(self.entries),
            "at": at,
            "endpoint_id": endpoint_id,
            "from_state": from_state,
            "to_state": to_state,
            "reason": reason,
            "actor": actor,
            "evidence": evidence or {},
            "prev_hash": self.entries[-1].hash if self.entries else GENESIS,
        }
        entry = AuditEntry(**body, hash=_digest(body))
        self.entries.append(entry)
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
                # A decision acknowledged to an approver must survive a crash.
                fh.flush()
                os.fsync(fh.fileno())
            self._seen_size = self.path.stat().st_size
        return entry

    def verify(self) -> ChainCheck:
        self._sync()
        return verify_entries(self.entries)

    def for_endpoint(self, endpoint_id: str) -> list[AuditEntry]:
        self._sync()
        return [e for e in self.entries if e.endpoint_id == endpoint_id]


def verify_entries(entries: list[AuditEntry]) -> ChainCheck:
    """Recompute every hash and every link. Reports the first failure."""
    prev = GENESIS
    for i, entry in enumerate(entries):
        if entry.seq != i:
            return ChainCheck(False, len(entries), i, f"sequence {entry.seq} at position {i}")
        if entry.prev_hash != prev:
            return ChainCheck(False, len(entries), i, "link to previous entry broken")
        if _digest(entry.body()) != entry.hash:
            return ChainCheck(False, len(entries), i, "content does not match its hash")
        prev = entry.hash
    return ChainCheck(True, len(entries))


def load(path: Path) -> list[AuditEntry]:
    out: list[AuditEntry] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(AuditEntry(**json.loads(line)))
    return out


def verify_file(path: Path) -> ChainCheck:
    return verify_entries(load(path))
