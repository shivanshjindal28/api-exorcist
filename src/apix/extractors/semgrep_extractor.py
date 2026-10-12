"""
Route extraction via Semgrep.

This is the design decision defended in the literature review [3]: Semgrep parses
source into an abstract syntax tree and matches route declarations structurally,
so the same rule works across formatting styles and a declaration written inside
a comment or a string literal does not match. A regular expression over source
cannot tell those apart.

Implementation note — metavariable transport
--------------------------------------------
Semgrep's OSS JSON output does not carry a `metavars` field, but it interpolates
metavariables into the rule `message`. The rule file therefore emits messages of
the form `APIX|path="/v1/x"|func=handler`, which are parsed back here. This is
the only unobvious part of the integration and it is why the rules and this
module have to change together.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from apix.extractors.base import (
    ExtractedRoute,
    looks_like_route,
    normalise_path,
)

RULES_FILE = Path(__file__).resolve().parent / "rules" / "routes.yaml"

#: Excluded from scanning. Dependencies, build output and test fixtures are not
#: a deployed API surface, and a route matched inside them is a false endpoint.
EXCLUDE_DIRS = (
    "node_modules", "venv", ".venv", "env", "__pycache__", "site-packages",
    "dist", "build", ".tox", ".mypy_cache", ".pytest_cache", ".git",
    "vendor", "third_party", "test", "tests", "spec", "__tests__",
    "migrations", "alembic",
)

#: rule id -> (HTTP method, framework)
_RULE_MAP = {
    "apix-py-fastapi-get": ("GET", "fastapi"),
    "apix-py-fastapi-post": ("POST", "fastapi"),
    "apix-py-fastapi-put": ("PUT", "fastapi"),
    "apix-py-fastapi-patch": ("PATCH", "fastapi"),
    "apix-py-fastapi-delete": ("DELETE", "fastapi"),
    "apix-py-flask-route": ("GET", "flask"),      # refined below from the source line
    "apix-js-express-get": ("GET", "express"),
    "apix-js-express-post": ("POST", "express"),
    "apix-js-express-put": ("PUT", "express"),
    "apix-js-express-delete": ("DELETE", "express"),
    "apix-java-spring-get": ("GET", "spring"),
    "apix-java-spring-post": ("POST", "spring"),
    "apix-java-spring-put": ("PUT", "spring"),
    "apix-java-spring-delete": ("DELETE", "spring"),
}

_MSG = re.compile(r"APIX\|path=(?P<path>.*?)\|func=(?P<func>.*)$", re.S)
_PREFIX_MSG = re.compile(r"APIXPREFIX\|var=(?P<var>.*?)\|prefix=(?P<prefix>.*)$", re.S)
_MOUNT_MSG = re.compile(r"APIXMOUNT\|prefix=(?P<prefix>.*)$", re.S)
_FLASK_METHODS = re.compile(r"methods\s*=\s*\[([^\]]*)\]")


def _matched_source(res: dict[str, Any]) -> str:
    """The source text of a match, read from the file rather than from Semgrep.

    Semgrep's `extra.lines` used to carry the matched source. Current releases
    return the literal string "requires login" there unless the CLI is signed
    in to Semgrep's cloud platform, so reading Flask's `methods=[...]` from it
    silently turned every Flask route into GET, and a DELETE beside a GET on
    the same path collapsed into one endpoint. The match's line span is still
    reported, so the text is read from the file on disk instead. `extra.lines`
    remains only a fallback, and never when it is the redaction marker.
    """
    start = int((res.get("start") or {}).get("line", 0) or 0)
    end = int((res.get("end") or {}).get("line", start) or start)
    path = res.get("path")
    if path and start > 0:
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
            return "\n".join(text.splitlines()[start - 1 : max(end, start)])
        except OSError:
            pass
    lines = str((res.get("extra") or {}).get("lines") or "")
    return "" if lines.strip() == "requires login" else lines


def _clean(literal: str) -> str:
    """Strip quotes from a matched string literal."""
    return literal.strip().strip("\"'").strip()


class SemgrepExtractor:
    """Runs Semgrep over a checked-out repository."""

    name = "semgrep"

    def __init__(self, timeout: int = 900) -> None:
        self.timeout = timeout
        self.last_error: str | None = None
        self.rejected: list[str] = []
        self.mount_prefixes: list[str] = []
        #: Mounts whose prefix is an expression, e.g. settings.API_V1_STR. Its
        #: value is only known by running the project's configuration, which a
        #: scanner must never do, so routes under it are marked unresolved.
        self.variable_mounts: list[str] = []

    # ------------------------------------------------------------------
    def available(self) -> bool:
        return shutil.which("semgrep") is not None

    # ------------------------------------------------------------------
    def extract(self, repo_root: Path) -> list[ExtractedRoute]:
        if not self.available():
            self.last_error = "semgrep not installed"
            return []

        cmd = [
            "semgrep", "scan",
            "--config", str(RULES_FILE),
            "--json", "--quiet",
            "--metrics=off",          # do not phone home about a customer's code
            "--no-git-ignore",        # vendored code is still deployed code
        ]
        # Directories that never contain a deployed API surface. Excluding them
        # is not only a speed measure: a route matched inside node_modules or a
        # test fixture is a false endpoint, and false endpoints in this system
        # become fabricated shadow APIs.
        for pattern in EXCLUDE_DIRS:
            cmd += ["--exclude", pattern]
        cmd.append(str(repo_root))
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self.timeout
            )
        except subprocess.TimeoutExpired:
            self.last_error = f"semgrep timed out after {self.timeout}s"
            return []

        if not proc.stdout.strip():
            tail = (proc.stderr or "").strip().splitlines()
            self.last_error = tail[-1] if tail else "semgrep produced no output"
            return []

        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            self.last_error = f"could not parse semgrep output: {exc}"
            return []

        return self._parse(data, repo_root)

    # ------------------------------------------------------------------
    def _parse(
        self, data: dict[str, Any], repo_root: Path
    ) -> list[ExtractedRoute]:
        out: list[ExtractedRoute] = []
        seen: set[tuple[str, str]] = set()

        results = data.get("results", [])
        file_prefix, mount_prefixes, variable_mounts = self._collect_prefixes(
            results, repo_root)
        self.variable_mounts = sorted(variable_mounts)
        # A single mount prefix used consistently across the application (the
        # overwhelmingly common case, e.g. everything under /api/v1) can be
        # applied with confidence. Several different ones cannot be attributed
        # to particular routers without real cross-file dataflow analysis, so
        # in that case nothing is applied and the routes are marked unresolved.
        self.mount_prefixes = sorted(mount_prefixes)
        global_mount = self.mount_prefixes[0] if len(mount_prefixes) == 1 else ""

        for res in results:
            rule_id = str(res.get("check_id", "")).split(".")[-1]
            if rule_id not in _RULE_MAP:
                continue
            method, framework = _RULE_MAP[rule_id]

            m = _MSG.search(res.get("extra", {}).get("message", ""))
            if not m:
                continue
            raw_path = m.group("path").strip()
            func = m.group("func").strip() or None

            declared = _clean(raw_path)
            if not looks_like_route(declared) and declared not in ("/", ""):
                self.rejected.append(raw_path)
                continue

            try:
                rel_for_prefix = str(
                    Path(res["path"]).resolve().relative_to(repo_root.resolve())
                ).replace("\\", "/")
            except (ValueError, KeyError):
                rel_for_prefix = ""

            router_prefix = file_prefix.get(rel_for_prefix, "")
            composed = f"{global_mount}{router_prefix}/{declared.lstrip('/')}"
            path = normalise_path(composed)
            # Unresolved when several literal mounts compete, or when the only
            # mounts are expressions whose value the scan cannot know. Before
            # the second case was tracked, a project mounting everything under
            # prefix=settings.API_V1_STR looked fully resolved: the web report
            # showed /users where the deployed path is /api/v1/users.
            resolved = bool(global_mount) or not (mount_prefixes or variable_mounts)

            # Flask carries its methods as an argument rather than in the
            # decorator name, so recover them from the matched source lines.
            methods = [method]
            if framework == "flask":
                fm = _FLASK_METHODS.search(_matched_source(res))
                if fm:
                    found = [
                        t.strip().strip("\"'").upper()
                        for t in fm.group(1).split(",")
                        if t.strip()
                    ]
                    methods = found or ["GET"]

            rel = rel_for_prefix or str(res.get("path", "?"))

            for meth in methods:
                key = (meth, path)
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    ExtractedRoute(
                        method=meth,
                        path=path,
                        file=rel.replace("\\", "/"),
                        line=int(res.get("start", {}).get("line", 0)),
                        function=func,
                        framework=framework,
                        declared_path=declared,
                        prefix_resolved=resolved,
                    )
                )

        return sorted(out, key=lambda r: (r.path, r.method))

    # ------------------------------------------------------------------
    def _collect_prefixes(
        self, results: list[dict[str, Any]], repo_root: Path
    ) -> tuple[dict[str, str], set[str], set[str]]:
        """Router prefixes per file, literal mount prefixes, and variable ones."""
        per_file: dict[str, str] = {}
        mounts: set[str] = set()
        variables: set[str] = set()

        for res in results:
            rule_id = str(res.get("check_id", "")).split(".")[-1]
            msg = res.get("extra", {}).get("message", "")

            if rule_id == "apix-py-router-prefix":
                m = _PREFIX_MSG.search(msg)
                if not m:
                    continue
                prefix = _clean(m.group("prefix"))
                if not prefix.startswith("/"):
                    continue
                try:
                    rel = str(
                        Path(res["path"]).resolve().relative_to(repo_root.resolve())
                    ).replace("\\", "/")
                except (ValueError, KeyError):
                    continue
                per_file[rel] = prefix.rstrip("/")

            elif rule_id == "apix-py-include-router":
                m = _MOUNT_MSG.search(msg)
                if not m:
                    continue
                raw = m.group("prefix").strip()
                prefix = _clean(raw)
                if prefix.startswith("/"):
                    mounts.add(prefix.rstrip("/"))
                elif raw and raw[0] not in "\"'" and len(raw) <= 120:
                    variables.add(raw)

        return per_file, mounts, variables
