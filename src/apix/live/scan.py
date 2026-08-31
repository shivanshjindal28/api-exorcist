"""
Orchestrating a scan of a real repository.

Mirrors `apix.pipeline.run_discovery`, but the connectors read a checkout rather
than the simulated estate, and only the three sources a repository can actually
speak for are declared to the classifier.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

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
    unresolved_prefix_routes: int = 0

    @property
    def unavailable(self) -> frozenset[Source]:
        return frozenset(Source) - self.consulted

    @property
    def actionable(self) -> list[Verdict]:
        return [v for v in self.verdicts if v.is_actionable]


def scan_repository(
    target: str,
    *,
    local_path: str | Path | None = None,
    verbose: bool = True,
) -> RepoScanResult:
    """Scan a GitHub repository (or a local checkout) end to end."""
    if local_path is not None:
        scan = RepoScan.from_path(local_path, slug=target)
    else:
        if verbose:
            print(f"Cloning {target} ...")
        scan = RepoScan.clone(target)

    try:
        code = RepoCodeConnector(scan)
        spec = RepoOpenAPIConnector(scan)
        # CI/CD reports per route, so it must run after code extraction.
        signals: list[DiscoverySignal] = []
        signals += code.run()
        signals += spec.run()
        signals += RepoCICDConnector(scan, code).run()

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
            unresolved_prefix_routes=sum(
                1 for r in code.routes if not r.prefix_resolved
            ),
        )
    finally:
        scan.close()
