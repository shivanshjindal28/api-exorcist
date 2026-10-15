"""
Orchestrating a scan of a real repository.

Mirrors `apix.pipeline.run_discovery`, but the connectors read a checkout rather
than the simulated estate, and only the three sources a repository can actually
speak for are declared to the classifier.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from apix.connectors.base import DiscoverySignal, Source
from apix.engine.rules import RuleClassifier
from apix.engine.verdict import Verdict
from apix.inventory.correlator import Correlator, InventoryRecord
from apix.live.connectors import (
    REPO_SOURCES,
    RepoCICDConnector,
    RepoCodeConnector,
    RepoOpenAPIConnector,
)
from apix.live.repo import RepoScan


@dataclass
class RepoScanResult:
    """Everything one repository scan produced, including what it could not see."""

    slug: str
    head_commit: str
    records: list[InventoryRecord]
    verdicts: list[Verdict]
    consulted: frozenset[Source]
    routes_found: int = 0
    spec_files: list[str] = field(default_factory=list)
    workflow_count: int = 0
    codeowners_rules: int = 0
    total_commits: int = 0
    extractor: str = ""
    extractor_error: str | None = None
    rejected_paths: list[str] = field(default_factory=list)
    #: Mount prefixes found as literals. When a project mounts its router with a
    #: variable (`prefix=settings.API_V1_STR`) this comes back empty, and the
    #: reported paths are relative to the API root rather than absolute.
    mount_prefixes: list[str] = field(default_factory=list)
    #: Endpoints whose handler was found through the spec's operationId
    #: (Connexion, API-first Spring) rather than a route declaration.
    spec_wired_routes: int = 0
    variable_mounts: list[str] = field(default_factory=list)
    unresolved_prefix_routes: int = 0
    #: Calls, gateway routes and topics read from the code (apix.live.deps).
    dependencies: Any = None
    #: What the project's own clients reference (apix.live.clients).
    client_refs: Any = None
    #: endpoint id -> deprecation markers found at its handler.
    code_markers: dict[str, list[str]] = field(default_factory=dict)
    #: Days since the most recent commit to any file: is the project active?
    newest_change_days: int | None = None
    #: Variable mount prefixes resolved from their literal assignment.
    resolved_mounts: dict[str, str] = field(default_factory=dict)

    @property
    def unavailable(self) -> frozenset[Source]:
        return frozenset(Source) - self.consulted

    @property
    def actionable(self) -> list[Verdict]:
        return [v for v in self.verdicts if v.is_actionable]


def _shape(path: str) -> str:
    return re.sub(r"\{[^}]*\}", "{}", path)


def _align_parameter_names(spec_signals: list[DiscoverySignal],
                           routes: list[Any]) -> list[DiscoverySignal]:
    """Give a spec operation the code's parameter names when only they differ.

    crAPI's code serves /vehicle/{carId}/location and its spec documents
    /vehicle/{vehicleId}/location. A framework cannot serve two routes that
    differ only in a parameter's name, so they are one endpoint; kept apart,
    the code side read as undocumented and the spec side as unimplemented.
    """
    by_shape = {(r.method, _shape(r.path)): r.path for r in routes}
    out: list[DiscoverySignal] = []
    for s in spec_signals:
        code_path = by_shape.get((s.method, _shape(s.path)))
        if code_path and code_path != s.path:
            s = dataclasses.replace(s, path=code_path, endpoint_id=f"{s.method} {code_path}",
                                    attributes={**s.attributes, "spec_path": s.path})
        out.append(s)
    return out


def scan_repository(
    target: str,
    *,
    local_path: str | Path | None = None,
    verbose: bool = True,
    progress: Callable[[str], None] | None = None,
) -> RepoScanResult:
    """Scan a GitHub repository (or a local checkout) end to end.

    `progress` receives one short sentence per stage, for a caller (the web
    app) that shows a scan as it runs rather than only when it ends.
    """
    def say(message: str) -> None:
        if progress is not None:
            progress(message)

    if local_path is not None:
        say("Reading the project files")
        scan = RepoScan.from_path(local_path, slug=target)
    else:
        if verbose:
            print(f"Cloning {target} ...")
        say(f"Downloading {target} from GitHub (with its commit history)")
        scan = RepoScan.clone(target)

    try:
        code = RepoCodeConnector(scan)
        spec = RepoOpenAPIConnector(scan)
        # CI/CD reports per route, so it must run after code extraction.
        signals: list[DiscoverySignal] = []
        say("Finding API routes in the source code (Semgrep)")
        signals += code.run()
        say("Reading OpenAPI / Swagger specifications")
        spec_signals = _align_parameter_names(spec.run(), code.routes)
        signals += spec_signals
        # Handlers wired by the spec's operationId instead of a decorator.
        from apix.extractors.base import ExtractedRoute
        from apix.live.operations import find_handlers

        declared = {r.endpoint_id for r in code.routes}
        wanted = {str(s.attributes["operation_id"]): s for s in spec_signals
                  if s.attributes.get("operation_id") and s.endpoint_id not in declared}
        spec_wired = 0
        for op_id, h in find_handlers(scan, set(wanted)).items():
            s = wanted[op_id]
            route = ExtractedRoute(
                method=s.method, path=s.path, file=h.file, line=h.line,
                function=op_id.rsplit(".", 1)[-1], framework=f"operationId ({h.language})",
                declared_path=s.path, prefix_resolved=True,
            )
            code.routes.append(route)
            signals.append(code.signal_for(route))
            spec_wired += 1
        say("Reading CI/CD pipelines and ownership")
        signals += RepoCICDConnector(scan, code).run()
        say("Reading calls, gateway routes and topics between services")
        from apix.live.deps import extract_dependencies

        dependencies = extract_dependencies(scan)
        say("Reading which endpoints this project's own clients use")
        from apix.live.clients import collect_client_refs
        from apix.live.evidence import code_markers

        clients = collect_client_refs(scan)
        markers: dict[str, list[str]] = {}
        sources: dict[str, str] = {}
        for route in code.routes:
            if route.file not in sources:
                try:
                    sources[route.file] = (scan.root / route.file).read_text(
                        encoding="utf-8", errors="replace")
                except OSError:
                    sources[route.file] = ""
            found = code_markers(sources[route.file], route.line)
            if found:
                markers[route.endpoint_id] = found
        say("Correlating and classifying")

        correlator = Correlator()
        correlator.ingest(signals)
        records = correlator.finalise()

        # Repository-derived ownership: CODEOWNERS reaches the record through
        # the CODE source, which the correlator does not know how to read.
        for rec in records:
            if rec.owner_team is None:
                owner = (rec.evidence.get(Source.CODE.value) or {}).get("codeowner")
                if owner:
                    rec.owner_team = owner
                    if "NO_OWNER" in rec.flags:
                        rec.flags.remove("NO_OWNER")

        verdicts = RuleClassifier(consulted=REPO_SOURCES).classify_all(records)

        return RepoScanResult(
            slug=scan.slug,
            head_commit=scan.head_commit,
            records=records,
            verdicts=verdicts,
            consulted=REPO_SOURCES,
            routes_found=len(code.routes),
            spec_files=spec.parsed_files,
            workflow_count=len(scan.workflow_files),
            codeowners_rules=len(scan.codeowners),
            total_commits=scan.total_commits,
            extractor=code.extractor.name,
            extractor_error=getattr(code.extractor, "last_error", None),
            rejected_paths=list(getattr(code.extractor, "rejected", []))[:20],
            mount_prefixes=list(getattr(code.extractor, "mount_prefixes", [])),
            variable_mounts=list(getattr(code.extractor, "variable_mounts", [])),
            unresolved_prefix_routes=sum(
                1 for r in code.routes if not r.prefix_resolved
            ),
            dependencies=dependencies,
            spec_wired_routes=spec_wired,
            client_refs=clients,
            code_markers=markers,
            newest_change_days=min(scan.file_age_days.values()) if scan.file_age_days else None,
            resolved_mounts=dict(getattr(code.extractor, "resolved_mounts", {})),
        )
    finally:
        scan.close()
