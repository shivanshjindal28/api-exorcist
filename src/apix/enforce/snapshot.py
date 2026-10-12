"""
A snapshot of a repository's API surface at one commit: what the code
declares, what the specification documents, and who owns each.

Two snapshots, the merge base and the pull request's head, are all that
enforcement compares. Nothing here touches traffic, so nothing here can say
whether an endpoint is used; enforcement makes no lifecycle claim at all, for
the same reason a repository scan abstains from one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from apix.extractors.base import ExtractedRoute, RouteExtractor, normalise_path
from apix.live.connectors import _load_spec
from apix.live.repo import RepoScan

_VERBS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")


@dataclass
class SpecEntry:
    file: str
    #: An explicit `x-owner` on the operation or the document's `info`. OpenAPI
    #: tags are deliberately not read as owners: they name functional groups
    #: ("users", "items"), and reading them as teams would let nearly any
    #: tagged endpoint pass an ownership check it has not earned.
    owner: str | None


@dataclass
class Snapshot:
    root: Path
    routes: dict[str, ExtractedRoute] = field(default_factory=dict)
    spec: dict[str, SpecEntry] = field(default_factory=dict)
    spec_files: list[str] = field(default_factory=list)
    spec_errors: list[str] = field(default_factory=list)
    _scan: RepoScan | None = None

    def codeowner(self, file: str) -> str | None:
        return self._scan.owner_of(file) if self._scan else None

    def documentation_of(self, route: ExtractedRoute) -> tuple[SpecEntry | None, bool]:
        """The spec entry documenting a route, and whether the match is certain.

        A route mounted under a prefix the extractor could not resolve has a
        relative path. It counts as documented if some documented path with the
        same method ends with it; that match is reported as uncertain rather
        than presented as fact.
        """
        exact = self.spec.get(route.endpoint_id)
        if exact or route.prefix_resolved:
            return exact, True
        for eid, entry in self.spec.items():
            method, _, path = eid.partition(" ")
            if method == route.method and path.endswith(route.path):
                return entry, False
        return None, False

    def owner_of(self, endpoint_id: str) -> str | None:
        route = self.routes.get(endpoint_id)
        if route:
            owner = self.codeowner(route.file)
            if owner:
                return owner
            entry, _ = self.documentation_of(route)
            return entry.owner if entry else None
        entry = self.spec.get(endpoint_id)
        return entry.owner if entry else None


def take_snapshot(root: Path, extractor: RouteExtractor) -> Snapshot:
    scan = RepoScan.from_path(root)
    snap = Snapshot(root=root, _scan=scan)
    for route in extractor.extract(root):
        snap.routes.setdefault(route.endpoint_id, route)
    for spec_path in scan.spec_files:
        rel = scan.rel(spec_path)
        try:
            doc = _load_spec(spec_path)
        except Exception as exc:
            snap.spec_errors.append(f"{rel}: {exc}")
            continue
        if isinstance(doc, dict) and isinstance(doc.get("paths"), dict):
            snap.spec_files.append(rel)
            _read_paths(doc, rel, snap)
    return snap


def _read_paths(doc: dict[str, Any], rel: str, snap: Snapshot) -> None:
    info = doc.get("info") if isinstance(doc.get("info"), dict) else {}
    doc_owner = info.get("x-owner") if isinstance(info, dict) else None
    for raw_path, ops in doc["paths"].items():
        if not isinstance(ops, dict):
            continue
        path = normalise_path(str(raw_path))
        for verb, op in ops.items():
            if str(verb).upper() not in _VERBS:
                continue
            op_owner = op.get("x-owner") if isinstance(op, dict) else None
            owner = op_owner or doc_owner
            snap.spec.setdefault(
                f"{str(verb).upper()} {path}",
                SpecEntry(file=rel, owner=str(owner) if owner else None),
            )
