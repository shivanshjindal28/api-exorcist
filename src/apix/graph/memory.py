"""
In-process dependency graph. The default, and the one the demo uses.

Deliberately dependency-free: the discovery pipeline, the classifier and now the
graph all run on the standard library alone, so `apix scan` needs no services
running. Neo4j is the deployment path, not a prerequisite for looking at the
tool. The traversal implemented here is the same one the Cypher query expresses.
"""

from __future__ import annotations

from collections import defaultdict, deque

from apix.graph.model import BlastRadius


class InMemoryGraph:
    """Adjacency-list dependency graph with breadth-first blast radius."""

    name = "in-memory"

    def __init__(self) -> None:
        # endpoint -> services observed calling it
        self._callers: dict[str, set[str]] = defaultdict(set)
        # service -> endpoints it exposes
        self._owns: dict[str, set[str]] = defaultdict(set)
        # endpoint -> owning service
        self._owner: dict[str, str] = {}

    # ------------------------------------------------------------------
    def add_endpoint(self, endpoint_id: str, service: str) -> None:
        self._owner[endpoint_id] = service
        self._owns[service].add(endpoint_id)

    def add_call(self, caller_service: str, endpoint_id: str) -> None:
        # A service calling its own endpoint is not a dependency worth
        # reporting; it would make every service depend on itself and inflate
        # every blast radius by one.
        if self._owner.get(endpoint_id) == caller_service:
            return
        self._callers[endpoint_id].add(caller_service)

    # ------------------------------------------------------------------
    def blast_radius(self, endpoint_id: str, max_depth: int = 4) -> BlastRadius:
        """Breadth-first over alternating CALLS and OWNS edges.

        Hop 1 is the services that call this endpoint. Those services can no
        longer serve their own endpoints reliably, so hop 2 is those endpoints,
        and hop 3 is whoever calls them — and so on outward.
        """
        direct = sorted(self._callers.get(endpoint_id, set()))
        if not direct:
            return BlastRadius(endpoint_id=endpoint_id)

        seen_services: set[str] = set(direct)
        seen_endpoints: set[str] = {endpoint_id}
        affected: list[tuple[str, int]] = []
        depth_reached = 1
        truncated = False

        # queue of (service, hop at which it was reached)
        queue: deque[tuple[str, int]] = deque((s, 1) for s in direct)

        while queue:
            service, hop = queue.popleft()
            if hop >= max_depth:
                truncated = truncated or bool(self._owns.get(service))
                continue

            for ep in sorted(self._owns.get(service, set())):
                if ep in seen_endpoints:
                    continue
                seen_endpoints.add(ep)
                affected.append((ep, hop + 1))
                depth_reached = max(depth_reached, hop + 1)

                for caller in sorted(self._callers.get(ep, set())):
                    if caller in seen_services:
                        continue
                    seen_services.add(caller)
                    depth_reached = max(depth_reached, hop + 2)
                    queue.append((caller, hop + 2))

        return BlastRadius(
            endpoint_id=endpoint_id,
            direct_services=direct,
            indirect_services=sorted(seen_services - set(direct)),
            affected_endpoints=affected,
            depth_reached=depth_reached,
            truncated=truncated,
        )

    # ------------------------------------------------------------------
    def stats(self) -> dict[str, int]:
        services = set(self._owns) | {
            s for callers in self._callers.values() for s in callers
        }
        return {
            "endpoints": len(self._owner),
            "services": len(services),
            "call_edges": sum(len(v) for v in self._callers.values()),
            "isolated_endpoints": sum(
                1 for e in self._owner if not self._callers.get(e)
            ),
        }

    def close(self) -> None:
        return None
