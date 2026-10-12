"""
Run enforcement for a repository: snapshot the merge base and the head, compare.

The base is the merge base of the target branch and HEAD, not the target
branch's tip. Comparing against the tip would attribute to this pull request
every endpoint merged to main since the branch was cut. The head is the working
tree as it stands, so the same command works in CI and as a local pre-push
check, uncommitted changes included.

The base is materialised with `git worktree add --detach` into a temporary
directory and removed afterwards. Nothing from the repository is executed:
routes are found by static analysis, and specifications are parsed as data.
"""

from __future__ import annotations

import contextlib
import subprocess
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from apix.enforce.check import Comparison, compare
from apix.enforce.config import EnforceConfig
from apix.enforce.snapshot import Snapshot, take_snapshot
from apix.extractors.base import RouteExtractor


class EnforceError(RuntimeError):
    """Enforcement could not run: not a repository, unknown ref, no extractor."""


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=300
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip().splitlines()
        raise EnforceError(f"git {' '.join(args)}: {detail[-1] if detail else 'failed'}")
    return proc.stdout.strip()


def merge_base(repo: Path, base_ref: str) -> str:
    _git(repo, "rev-parse", "--is-inside-work-tree")
    try:
        _git(repo, "rev-parse", "--verify", f"{base_ref}^{{commit}}")
    except EnforceError:
        raise EnforceError(
            f"unknown base ref {base_ref!r}. In CI, check out with fetch-depth: 0 "
            "so the base branch's history is present."
        ) from None
    return _git(repo, "merge-base", base_ref, "HEAD")


@contextlib.contextmanager
def checkout(repo: Path, commit: str) -> Iterator[Path]:
    """A detached, temporary worktree of `commit`, removed on exit."""
    with tempfile.TemporaryDirectory(prefix="apix-base-") as tmp:
        target = Path(tmp) / "base"
        _git(repo, "worktree", "add", "--detach", "--quiet", str(target), commit)
        try:
            yield target
        finally:
            with contextlib.suppress(EnforceError):
                _git(repo, "worktree", "remove", "--force", str(target))


@dataclass
class EnforceResult:
    base_ref: str
    base_commit: str
    config: EnforceConfig
    base: Snapshot
    head: Snapshot
    comparison: Comparison


def run_enforcement(
    repo: Path,
    base_ref: str,
    extractor: RouteExtractor,
    config: EnforceConfig | None = None,
) -> EnforceResult:
    repo = repo.resolve()
    if not extractor.available():
        raise EnforceError(
            f"route extractor {extractor.name!r} is not available. "
            'Install it with: pip install -e ".[live]"'
        )
    cfg = config or EnforceConfig.load(repo)
    commit = merge_base(repo, base_ref)
    with checkout(repo, commit) as base_root:
        base = take_snapshot(base_root, extractor)
    head = take_snapshot(repo, extractor)
    return EnforceResult(
        base_ref=base_ref,
        base_commit=commit,
        config=cfg,
        base=base,
        head=head,
        comparison=compare(base, head, cfg),
    )
