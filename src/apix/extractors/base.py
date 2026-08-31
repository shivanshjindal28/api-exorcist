"""
What a route extractor returns, and what one must implement.

Extractors are deliberately dumb: they report route declarations found in
source, and nothing else. They do not decide whether a route is deployed, used,
documented or dangerous — those are questions for the correlator and the engine,
answered by combining this with other sources.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

#: HTTP methods we recognise. Anything else is ignored rather than guessed at.
METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")


@dataclass(frozen=True)
class ExtractedRoute:
    """One route declaration found in source code."""

    method: str
    path: str
    file: str            # repo-relative
    line: int
    function: str | None = None
    framework: str | None = None
    #: The path exactly as written at the declaration, before any router or
    #: mount prefix was applied. Kept so a reader can see what was inferred.
    declared_path: str | None = None
    #: False when the route hangs off a router whose mount point could not be
    #: resolved, so `path` is relative and incomplete. Reported rather than
    #: hidden: a partially-known path is useful, a silently wrong one is not.
    prefix_resolved: bool = True

    @property
    def endpoint_id(self) -> str:
        return f"{self.method} {self.path}"


class RouteExtractor(Protocol):
    """Anything that can find route declarations in a checked-out repository."""

    name: str

    def available(self) -> bool:
        """Whether this extractor can run in the current environment."""
        ...

    def extract(self, repo_root: Path) -> list[ExtractedRoute]:
        ...


# ---------------------------------------------------------------------------
# Path normalisation
# ---------------------------------------------------------------------------
#: Frameworks spell path parameters differently. Normalising them is what lets a
#: route found in code be matched against the same route in an OpenAPI spec —
#: without it, `/users/{id}` and `/users/:id` are two different endpoints and the
#: correlator reports a shadow API that does not exist.
#
# Order matters and is load-bearing. The Express pattern `:name` also matches
# inside Flask's `<int:id>`, turning it into `<int{id}>` and leaving the angle
# brackets behind. The more specific delimited forms must therefore be rewritten
# before the bare-colon one.
_PARAM_PATTERNS = [
    (re.compile(r"\(\?P<([A-Za-z_][A-Za-z0-9_]*)>[^)]*\)"), r"{\1}"),   # Django
    (re.compile(r"<(?:[A-Za-z_][A-Za-z0-9_]*:)?([A-Za-z_][A-Za-z0-9_]*)>"),
     r"{\1}"),                                                          # Flask
    (re.compile(r":([A-Za-z_][A-Za-z0-9_]*)"), r"{\1}"),                # Express
]


def normalise_path(path: str) -> str:
    """Canonicalise a route path for cross-source matching.

    Parameter *names* are preserved rather than blanked. Two endpoints that
    differ only in parameter name are genuinely different endpoints, and
    collapsing them would merge records that should stay separate.
    """
    p = path.strip().strip("\"'")
    for pattern, repl in _PARAM_PATTERNS:
        p = pattern.sub(repl, p)
    if not p.startswith("/"):
        p = "/" + p
    # Collapse duplicate slashes, drop a trailing one (but keep root "/").
    p = re.sub(r"/{2,}", "/", p)
    if len(p) > 1:
        p = p.rstrip("/")
    return p


def looks_like_route(path: str) -> bool:
    """Reject values that are clearly not URL paths.

    Semgrep matches `$APP.get(...)` structurally, which also catches things like
    `config.get("timeout")` and `session.get(url)`. Filtering those out here is
    cheaper and more honest than writing ever-more-specific patterns, and the
    rejects are reported so the filter itself can be audited.
    """
    if not path or len(path) > 300:
        return False
    if path.startswith(("http://", "https://")):
        return False   # an outbound call, not a route this service serves
    # A route path is a literal string; a variable reference is not usable.
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", path):
        return False
    if any(c in path for c in " \t\n\"'`"):
        return False
    return path.startswith("/") or "/" in path
