"""
Acquiring a real repository and reading real facts out of it.

This module is where the project stops being a simulation. Everything it
reports is observed from an actual checkout: route declarations parsed from
source, per-file staleness taken from commit history, ownership read from
CODEOWNERS, deployment evidence from workflow files.

Safety
------
Nothing from the cloned repository is executed. Files are read and parsed, never
run, and Semgrep analyses source as data. Clones are made with credentials
absent by default, so a scan of a public repository is an ordinary anonymous
fetch.

Cost
----
Cloned with `--filter=blob:none`: full commit history arrives (which is what
staleness needs) while file contents are fetched lazily. A shallow `--depth 1`
clone would be faster but would destroy exactly the signal we came for.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

#: Directories that contain code which is never a deployed API surface.
_SKIP_DIRS = {
    ".git", "node_modules", "venv", ".venv", "env", "__pycache__",
    "site-packages", "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
    "vendor", "third_party", "examples", "example", "docs", "doc",
}

_SPEC_NAMES = re.compile(
    r"(openapi|swagger)[.\-_]?.*\.(json|ya?ml)$|"
    r".*\.(openapi|swagger)\.(json|ya?ml)$",
    re.I,
)

_CODEOWNERS_LOCATIONS = (
    "CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS", ".gitlab/CODEOWNERS",
)


class RepoError(RuntimeError):
    """Raised when a repository cannot be acquired or read."""


@dataclass
class RepoScan:
    """A checked-out repository and the facts observed from it."""

    slug: str                       # "owner/name"
    root: Path
    _tempdir: tempfile.TemporaryDirectory[str] | None = None

    #: repo-relative path -> days since that file was last committed
    file_age_days: dict[str, int] = field(default_factory=dict)
    #: glob pattern -> owners, from CODEOWNERS
    codeowners: list[tuple[str, list[str]]] = field(default_factory=list)
    spec_files: list[Path] = field(default_factory=list)
    workflow_files: list[Path] = field(default_factory=list)
    default_branch: str = ""
    head_commit: str = ""
    total_commits: int = 0

    # ------------------------------------------------------------------
    @classmethod
    def clone(cls, slug: str, *, depth: int | None = None) -> RepoScan:
        """Clone `owner/name` from GitHub into a temporary directory."""
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", slug):
            raise RepoError(
                f"expected a GitHub repository as owner/name, got {slug!r}"
            )
        if shutil.which("git") is None:
            raise RepoError("git is not installed")

        td = tempfile.TemporaryDirectory(prefix="apix-scan-")
        dest = Path(td.name) / slug.split("/")[-1]
        url = f"https://github.com/{slug}.git"

        cmd = ["git", "clone", "--filter=blob:none", "--quiet"]
        if depth:
            cmd += ["--depth", str(depth)]
        cmd += [url, str(dest)]

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if proc.returncode != 0:
            td.cleanup()
            err = (proc.stderr or "").strip().splitlines()
            detail = err[-1] if err else "unknown error"
            raise RepoError(f"could not clone {slug}: {detail}")

        scan = cls(slug=slug, root=dest, _tempdir=td)
        scan._gather()
        return scan

    @classmethod
    def from_path(cls, path: str | Path, slug: str | None = None) -> RepoScan:
        """Use an already-present checkout, for tests and offline scans."""
        root = Path(path).resolve()
        if not root.exists():
            raise RepoError(f"no such directory: {root}")
        scan = cls(slug=slug or root.name, root=root)
        scan._gather()
        return scan

    # ------------------------------------------------------------------
    def _git(self, *args: str) -> str:
        proc = subprocess.run(
            ["git", "-C", str(self.root), *args],
            capture_output=True, text=True, timeout=600,
        )
        return proc.stdout if proc.returncode == 0 else ""

    def _gather(self) -> None:
        self.default_branch = self._git(
            "rev-parse", "--abbrev-ref", "HEAD"
        ).strip()
        self.head_commit = self._git("rev-parse", "--short", "HEAD").strip()
        self._read_file_ages()
        self._read_codeowners()
        self._find_specs_and_workflows()

    # ------------------------------------------------------------------
    def _read_file_ages(self) -> None:
        """Per-file days-since-last-commit, in a single pass over history.

        Asking git per file would be one process per file — minutes on a large
        repository. One `--name-only` walk gives the same answer in one pass,
        and the first time a path appears is by definition its most recent
        commit because the log is in reverse chronological order.
        """
        out = self._git("log", "--name-only", "--format=%ct", "--no-merges")
        if not out:
            return

        now = datetime.now(timezone.utc).timestamp()
        current_ts: float | None = None
        commits = 0
        for line in out.splitlines():
            line = line.rstrip()
            if not line:
                continue
            if line.isdigit():
                current_ts = float(line)
                commits += 1
                continue
            if current_ts is None:
                continue
            path = line.replace("\\", "/")
            if path not in self.file_age_days:
                self.file_age_days[path] = int((now - current_ts) / 86400)
        self.total_commits = commits

    def _read_codeowners(self) -> None:
        for rel in _CODEOWNERS_LOCATIONS:
            f = self.root / rel
            if not f.is_file():
                continue
            for raw in f.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = raw.split("#", 1)[0].strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    self.codeowners.append((parts[0], parts[1:]))
            break

    def _find_specs_and_workflows(self) -> None:
        wf_dir = self.root / ".github" / "workflows"
        if wf_dir.is_dir():
            self.workflow_files = sorted(
                p for p in wf_dir.iterdir()
                if p.suffix.lower() in (".yml", ".yaml")
            )

        for p in self._walk():
            if _SPEC_NAMES.search(p.name):
                self.spec_files.append(p)

    def _walk(self) -> Iterator[Path]:
        for p in self.root.rglob("*"):
            if not p.is_file():
                continue
            if any(part in _SKIP_DIRS for part in p.relative_to(self.root).parts):
                continue
            yield p

    # ------------------------------------------------------------------
    def rel(self, p: Path) -> str:
        return str(p.relative_to(self.root)).replace("\\", "/")

    def age_of(self, rel_path: str) -> int | None:
        """Days since `rel_path` was last committed, if history knows."""
        return self.file_age_days.get(rel_path.replace("\\", "/"))

    def owner_of(self, rel_path: str) -> str | None:
        """CODEOWNERS owner for a path.

        Later entries win, matching git's own precedence rule.
        """
        match: str | None = None
        for pattern, owners in self.codeowners:
            if self._codeowner_matches(pattern, rel_path) and owners:
                match = owners[0].lstrip("@")
        return match

    @staticmethod
    def _codeowner_matches(pattern: str, path: str) -> bool:
        pat = pattern.strip()
        if pat in ("*", "**"):
            return True
        pat = pat.lstrip("/")
        if pat.endswith("/"):
            return path.startswith(pat)
        if "*" not in pat:
            return path == pat or path.startswith(pat.rstrip("/") + "/")
        regex = re.escape(pat).replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
        return re.fullmatch(regex, path) is not None

    def close(self) -> None:
        if self._tempdir is not None:
            self._tempdir.cleanup()
            self._tempdir = None

    def __enter__(self) -> RepoScan:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
