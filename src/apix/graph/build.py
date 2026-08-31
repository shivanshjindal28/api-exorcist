"""
Building the dependency graph from the inventory, and gating removals on it.

This is where the graph earns its place: a ZOMBIE verdict is a *hypothesis* that
an endpoint is unused. The graph is the first thing that can falsify it. An
endpoint nothing calls may proceed to Safe Kill; one that something still calls
is blocked, and the blocking dependents are named.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from apix.engine.verdict import Verdict
from apix.graph.memory import InMemoryGraph
from apix.graph.model import BlastRadius, DependencyGraph
from apix.inventory.correlator import InventoryRecord


def get_graph() -> DependencyGraph:
    """Select the graph backend from the environment.

    APIX_GRAPH=neo4j switches to Neo4j; anything else uses the in-process graph,
    so the default path needs nothing running.
    """
    if os.environ.get("APIX_GRAPH", "memory").lower() == "neo4j":
        from apix.graph.neo4j_store import Neo4jGraph

        return Neo4jGraph()
    return InMemoryGraph()


def build_graph(
    records: list[InventoryRecord], graph: DependencyGraph | None = None
) -> DependencyGraph:
    """Load the correlated inventory into a dependency graph."""
    g = graph or get_graph()
    for rec in records:
        g.add_endpoint(rec.endpoint_id, rec.service)
    for rec in records:
        for caller in rec.caller_services:
            g.add_call(caller, rec.endpoint_id)
    return g


# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RemovalAssessment:
    """Whether an endpoint may proceed toward Safe Kill, and why."""

    verdict: Verdict
    radius: BlastRadius

    @property
    def may_proceed(self) -> bool:
        """Both the classifier and the graph must agree.

        The classifier says an endpoint looks dead; the graph says nothing
        depends on it. Either one alone is insufficient - the classifier can be
        wrong about usage, and an isolated endpoint that is still healthy should
        not be removed just because nobody calls it *yet*.
        """
        return self.verdict.is_actionable and self.radius.is_isolated

    @property
    def blocked_by(self) -> str | None:
        if not self.verdict.is_actionable:
            return self.verdict.blocked_reason or (
                f"classified {self.verdict.label.value}, not a removal candidate"
            )
        if not self.radius.is_isolated:
            names = ", ".join(self.radius.all_services[:4])
            more = len(self.radius.all_services) - 4
            suffix = f" (+{more} more)" if more > 0 else ""
            return (
                f"blocked: {len(self.radius.all_services)} service(s) still "
                f"depend on this endpoint — {names}{suffix}"
            )
        return None

    def to_dict(self) -> dict[str, object]:
        return {
            "endpoint_id": self.verdict.endpoint_id,
            "label": self.verdict.label.value,
            "may_proceed": self.may_proceed,
            "blocked_by": self.blocked_by,
            "blast_radius": self.radius.to_dict(),
        }


def assess_removals(
    verdicts: list[Verdict],
    graph: DependencyGraph,
    max_depth: int = 4,
) -> list[RemovalAssessment]:
    """Assess every removal candidate against the dependency graph."""
    out: list[RemovalAssessment] = []
    for v in verdicts:
        if v.label.value != "ZOMBIE":
            continue
        out.append(
            RemovalAssessment(
                verdict=v, radius=graph.blast_radius(v.endpoint_id, max_depth)
            )
        )
    return sorted(out, key=lambda a: (not a.may_proceed, a.verdict.endpoint_id))
