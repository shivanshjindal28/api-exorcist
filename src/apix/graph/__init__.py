"""Dependency graph and blast-radius analysis.

The prerequisite for Safe Kill: before an endpoint can be disabled, the system
must be able to say what would break. In-memory by default so nothing needs to
be running; Neo4j for deployment, via the same interface.
"""

from apix.graph.build import (
    RemovalAssessment,
    assess_removals,
    build_graph,
    get_graph,
)
from apix.graph.memory import InMemoryGraph
from apix.graph.model import BlastRadius, DependencyGraph

__all__ = [
    "BlastRadius",
    "DependencyGraph",
    "InMemoryGraph",
    "RemovalAssessment",
    "assess_removals",
    "build_graph",
    "get_graph",
]
