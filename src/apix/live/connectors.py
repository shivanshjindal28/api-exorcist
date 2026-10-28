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
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from apix.connectors.base import Connector, DiscoverySignal, Source
from apix.extractors.base import ExtractedRoute, normalise_path
from apix.extractors.semgrep_extractor import SemgrepExtractor
from apix.live.repo import RepoScan, service_directories, service_of

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
            yield self.signal_for(r)

    def signal_for(self, r: ExtractedRoute) -> DiscoverySignal:
        """The CODE signal for one route; also used for spec-wired handlers."""
        age = self.scan.age_of(r.file)
        owner = self.scan.owner_of(r.file)
        return DiscoverySignal(
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
                # What the reader needs to check the route against the source:
                # the path as written at the declaration, and whether the
                # prefix in front of it is known or could not be determined.
                "declared_path": r.declared_path,
                "prefix_resolved": r.prefix_resolved,
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
        self._services: set[str] | None = None

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
        prefix = _server_prefix(doc)
        for raw_path, ops in paths.items():
            if not isinstance(ops, dict):
                continue
            path = normalise_path(prefix + str(raw_path))
            service = self._service_for(path, spec_path)
            for verb, op in ops.items():
                if verb.upper() not in (
                    "GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"
                ):
                    continue
                op = op if isinstance(op, dict) else {}
                yield DiscoverySignal(
                    source=self.source,
                    endpoint_id=f"{verb.upper()} {path}",
                    service=service,
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
                        "operation_id": op.get("operationId"),
                        "spec_summary": str(op.get("summary") or "")[:200],
                    },
                )


    def _service_for(self, path: str, spec_path: Path) -> str:
        """The service an operation belongs to.

        Where the spec file sits is a poor guide when one spec documents several
        services: crAPI's openapi-spec/ folder made a "service" of that name out
        of every Django and Go endpoint, whose routes are known only from the
        spec. A path whose first segment names a service folder in the
        repository (/workshop/api/... beside services/workshop) belongs to it.
        """
        if self._services is None:
            self._services = service_directories(self.scan.root)
        first = path.strip("/").split("/", 1)[0]
        if first in self._services:
            return first
        return _service_of(self.scan.rel(spec_path))


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
def _server_prefix(doc: dict[str, Any]) -> str:
    """The path every operation sits under: Swagger 2 basePath, or OpenAPI 3's
    first server URL's path. "/owners" under a server of "/petclinic/api" is
    served at /petclinic/api/owners, which is the path the code declares."""
    base = doc.get("basePath")
    if isinstance(base, str) and base.startswith("/"):
        return base.rstrip("/")
    servers = doc.get("servers")
    if isinstance(servers, list) and servers and isinstance(servers[0], dict):
        url = str(servers[0].get("url") or "")
        path = re.sub(r"^[a-z]+://[^/]*", "", url)
        if path.startswith("/") and "{" not in path:
            return path.rstrip("/")
    return ""


def _load_spec(path: Path) -> Any:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    # yaml.safe_load: never construct arbitrary Python objects from a file that
    # came out of someone else's repository.
    # Imported here, not at module level: the REST API imports this module
    # through the scanning code, and a server installed with only the api
    # extra (the container image) has no PyYAML. A top-level import made the
    # container fail to start; CI's container job caught it.
    import yaml

    return yaml.safe_load(text)


def _service_of(rel_path: str) -> str:
    """Infer a service name from where the file sits in the tree."""
    return service_of(rel_path)


def _version_of(path: str) -> str:
    for seg in path.strip("/").split("/"):
        if len(seg) >= 2 and seg[0] == "v" and seg[1:].isdigit():
            return seg
    return "unversioned"


def _owner_from_spec(doc: dict[str, Any], op: dict[str, Any]) -> str | None:
    """An owner the spec states explicitly (x-owner / x-team), or None.

    Tags are functional groupings ("users", "books"), not teams, and the info
    contact is whoever answers questions about the document. Reading either as
    an owner made VAmPI report every endpoint as owned when it names no owner
    anywhere. Enforcement has always used this same rule.
    """
    for source in (op, doc.get("info") or {}, doc):
        if isinstance(source, dict):
            for key in ("x-owner", "x-team", "x-owning-team"):
                if source.get(key):
                    return str(source[key])
    return None


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
