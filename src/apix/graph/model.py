"""
The dependency graph: what would break if an endpoint disappeared.

Why a graph rather than a table
-------------------------------
The question Safe Kill has to answer is "what transitively depends on this
endpoint?", and the depth is not known in advance. In SQL that is a recursive
common table expression whose cost grows with each hop and whose query text
obscures the intent; in a graph it is a variable-length path match. Since this
query runs on every removal decision, the store is chosen for the query we run
most, not for the one that is easiest to set up.

This is not our inference from a paper about graphs in general. Ma et al. [4]
build a Service Dependency Graph for microservices *in Neo4j* and evaluate its
generation from ten to hundreds of services; Abdelfattah and Cerný [5] formalise
inter-service dependency as a first-class, measurable architectural property.
Where we diverge from [4] is purpose: they use the graph for comprehension and
regression-test selection, we use it as a safety gate on removal.

Model
-----
    (Service)-[:CALLS]->(Endpoint)      observed on the wire
    (Service)-[:OWNS]->(Endpoint)       the service exposing it

Blast radius alternates those two edge types: killing an endpoint breaks the
services that call it; those services then fail to serve their own endpoints;
whatever called *those* is affected in turn. Traversing only CALLS would stop at
one hop and report a blast radius far smaller than the truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class BlastRadius:
    """What removing one endpoint would affect."""

    endpoint_id: str
    #: Services that call this endpoint directly.
    direct_services: list[str] = field(default_factory=list)
    #: Services reached only through further hops.
    indirect_services: list[str] = field(default_factory=list)
    #: Endpoints that would themselves degrade, with the hop at which they appear.
    affected_endpoints: list[tuple[str, int]] = field(default_factory=list)
    depth_reached: int = 0
    truncated: bool = False

    @property
    def all_services(self) -> list[str]:
        return sorted({*self.direct_services, *self.indirect_services})

    @property
    def is_isolated(self) -> bool:
        """Nothing observed depends on this endpoint.

        The precondition for Safe Kill. Note what this does *not* say: it says
        no dependency was observed, not that none exists. A caller that was
        silent during the capture window is invisible here, which is why the
        approval gate and the canary rollout exist downstream rather than the
        graph being treated as proof.
        """
        return not self.direct_services and not self.indirect_services

    @property
    def severity(self) -> str:
        n = len(self.all_services)
        if n == 0:
            return "isolated"
        if n <= 2:
            return "contained"
        if n <= 5:
            return "broad"
        return "severe"

    def to_dict(self) -> dict[str, Any]:
        return {
            "endpoint_id": self.endpoint_id,
            "direct_services": self.direct_services,
            "indirect_services": self.indirect_services,
            "affected_endpoints": [
                {"endpoint_id": e, "hop": h} for e, h in self.affected_endpoints
            ],
            "depth_reached": self.depth_reached,
            "truncated": self.truncated,
            "isolated": self.is_isolated,
            "severity": self.severity,
        }


class DependencyGraph(Protocol):
    """Storage-agnostic dependency graph.

    Two implementations: an in-process one used by default, and Neo4j for
    deployment. The pipeline code is identical either way, exactly as with the
    message bus — a demo must not depend on a database being up.
    """

    name: str

    def add_endpoint(self, endpoint_id: str, service: str) -> None: ...

    def add_call(self, caller_service: str, endpoint_id: str) -> None: ...

    def blast_radius(self, endpoint_id: str, max_depth: int = 4) -> BlastRadius: ...

    def stats(self) -> dict[str, int]: ...

    def close(self) -> None: ...
