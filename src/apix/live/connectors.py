"""
Discovery connectors that read a real repository.

These emit the same `DiscoverySignal` objects as the simulated connectors, so
the correlator, the classifier and the explanation layer are entirely unchanged.
That interchangeability is the point of the connector contract, and this module
is the first proof that it actually holds.

What a repository can and cannot tell you
-----------------------------------------
    CODE     yes - route declarations, per-file commit staleness, CODEOWNERS
    OPENAPI  yes - specs committed to the repository
    CICD     yes - workflow definitions, i.e. whether a pipeline exists
    GATEWAY  no  - lives in the customer's runtime, not their source
    TRAFFIC  no  - requires a network sensor
    DNS      no  - requires resolver access

The three absent sources are not gaps to paper over. They are declared to the
classifier so that rules depending on them abstain, which is what stops a
repository scan from calling every endpoint a zombie.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml

from apix.connectors.base import Connector, DiscoverySignal, Source
from apix.extractors.base import ExtractedRoute, normalise_path
from apix.extractors.semgrep_extractor import SemgrepExtractor
from apix.live.repo import RepoScan

#: The sources a repository scan can actually speak for.
REPO_SOURCES: frozenset[Source] = frozenset(
    {Source.CODE, Source.OPENAPI, Source.CICD}
)


class RepoCodeConnector(Connector):
    """Route declarations extracted from source, with real commit staleness."""

    source = Source.CODE
    name = "semgrep-repo"

    def __init__(self, scan: RepoScan, extractor: Any = None) -> None:
        self.scan = scan
        self.extractor = extractor or SemgrepExtractor()
        self.routes: list[ExtractedRoute] = []

    def collect(self) -> Iterator[DiscoverySignal]:
        self.routes = self.extractor.extract(self.scan.root)
        for r in self.routes:
            age = self.scan.age_of(r.file)
            owner = self.scan.owner_of(r.file)
            yield DiscoverySignal(
                source=self.source,
                endpoint_id=r.endpoint_id,
                service=_service_of(r.file),
                method=r.method,
                path=r.path,
                version=_version_of(r.path),
                attributes={
                    "handler_exists_in_code": True,
                    "days_since_last_commit": age,
                    "source_file": r.file,
                    "source_line": r.line,
                    "handler_function": r.function,
                    "framework": r.framework,
                    # CODEOWNERS is a genuine ownership signal and the reason a
                    # repository scan can answer "who owns this?" at all.
                    "codeowner": owner,
                },
            )


class RepoOpenAPIConnector(Connector):
    """Endpoints declared in OpenAPI/Swagger documents committed to the repo."""

    source = Source.OPENAPI
    name = "openapi-repo"

    def __init__(self, scan: RepoScan) -> None:
        self.scan = scan
        self.parsed_files: list[str] = []
        self.parse_errors: list[str] = []

    def collect(self) -> Iterator[DiscoverySignal]:
        for spec_path in self.scan.spec_files:
            try:
                doc = _load_spec(spec_path)
            except Exception as exc:
                self.parse_errors.append(f"{self.scan.rel(spec_path)}: {exc}")
                continue
            if not isinstance(doc, dict) or "paths" not in doc:
                continue
            self.parsed_files.append(self.scan.rel(spec_path))
            yield from self._from_document(doc, spec_path)

    def _from_document(
        self, doc: dict[str, Any], spec_path: Path
    ) -> Iterator[DiscoverySignal]:
        paths = doc.get("paths") or {}
        if not isinstance(paths, dict):
            return
        for raw_path, ops in paths.items():
            if not isinstance(ops, dict):
                continue
            path = normalise_path(str(raw_path))
            for verb, op in ops.items():
                if verb.upper() not in (
                    "GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"
                ):
                    continue
                op = op if isinstance(op, dict) else {}
                yield DiscoverySignal(
                    source=self.source,
                    endpoint_id=f"{verb.upper()} {path}",
                    service=_service_of(self.scan.rel(spec_path)),
                    method=verb.upper(),
                    path=path,
                    version=_version_of(path),
                    attributes={
                        "documented": True,
                        # The OpenAPI `deprecated` flag: a real observable, and
                        # an imperfect one, because teams forget to set it.
                        "spec_deprecated": bool(op.get("deprecated", False)),
                        "owner_team": _owner_from_spec(doc, op),
                        "declared_auth": _auth_from_spec(doc, op),
                        "spec_file": self.scan.rel(spec_path),
                    },
                )


class RepoCICDConnector(Connector):
    """Whether a deployment pipeline exists that could have shipped this code.

    A repository cannot show deployment *events* without the Actions API, so
    this reports the weaker but honest fact: a pipeline is defined, or it is not.
    """

    source = Source.CICD
    name = "workflows-repo"

    def __init__(self, scan: RepoScan, code: RepoCodeConnector) -> None:
        self.scan = scan
        self.code = code

    def collect(self) -> Iterator[DiscoverySignal]:
        has_pipeline = bool(self.scan.workflow_files)
        if not has_pipeline:
            return
        for r in self.code.routes:
            yield DiscoverySignal(
                source=self.source,
                endpoint_id=r.endpoint_id,
                service=_service_of(r.file),
                method=r.method,
                path=r.path,
                version=_version_of(r.path),
                attributes={
                    "deployed_via_pipeline": True,
                    "pipeline_owner_team": self.scan.owner_of(r.file),
                    "workflow_count": len(self.scan.workflow_files),
                },
            )


# ---------------------------------------------------------------------------
def _load_spec(path: Path) -> Any:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    # yaml.safe_load: never construct arbitrary Python objects from a file that
    # came out of someone else's repository.
    return yaml.safe_load(text)


def _service_of(rel_path: str) -> str:
    """Infer a service name from where the file sits in the tree."""
    parts = [p for p in rel_path.split("/") if p]
    if len(parts) > 1:
        return parts[0]
    return "root"


def _version_of(path: str) -> str:
    for seg in path.strip("/").split("/"):
        if len(seg) >= 2 and seg[0] == "v" and seg[1:].isdigit():
            return seg
    return "unversioned"


def _owner_from_spec(doc: dict[str, Any], op: dict[str, Any]) -> str | None:
    tags = op.get("tags")
    if isinstance(tags, list) and tags:
        return str(tags[0])
    contact = (doc.get("info") or {}).get("contact") or {}
    name = contact.get("name")
    return str(name) if name else None


def _auth_from_spec(doc: dict[str, Any], op: dict[str, Any]) -> str | None:
    sec = op.get("security", doc.get("security"))
    if sec == []:
        return "NONE"          # explicitly opting out of global security
    if not sec:
        return None            # unstated, which is not the same as none
    schemes = (doc.get("components") or {}).get("securitySchemes") or {}
    for entry in sec if isinstance(sec, list) else []:
        for key in entry or {}:
            s = schemes.get(key) or {}
            t = str(s.get("type", "")).lower()
            if t == "oauth2":
                return "OAUTH2"
            if t == "http" and str(s.get("scheme", "")).lower() == "bearer":
                return "JWT"
            if t == "apikey":
                return "API_KEY"
    return None
