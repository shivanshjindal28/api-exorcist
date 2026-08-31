"""
Neo4j-backed dependency graph: the deployment path.

The Cypher below is the point of the whole design decision. Blast radius is a
variable-length path match:

    MATCH path = (s:Service)-[:CALLS|OWNS*1..N]->(e:Endpoint {id: $id})

In a relational store the same question is a recursive CTE whose cost grows with
each hop and whose SQL text buries the intent. Since this query runs on every
removal decision and its depth is not known in advance, the store is chosen for
the query we run most often.

The driver is imported lazily and the module fails loudly rather than silently:
if Neo4j is configured but unreachable, that is a real error, not something to
paper over with an empty result.
"""

from __future__ import annotations

from typing import Any

from apix.graph.model import BlastRadius


class Neo4jGraph:
    """Dependency graph stored in Neo4j."""

    name = "neo4j"

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str = "neo4j",
    ) -> None:
        import os

        try:
            from neo4j import GraphDatabase
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "Neo4jGraph requires the neo4j driver. Install it with "
                'pip install -e ".[graph]", or use the in-memory graph '
                "(the default), which needs no services running."
            ) from exc

        self.uri = uri or os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        self.database = database
        auth = (
            user or os.environ.get("NEO4J_USER", "neo4j"),
            password or os.environ.get("NEO4J_PASSWORD", ""),
        )
        self._driver = GraphDatabase.driver(self.uri, auth=auth)
        self._ensure_constraints()

    # ------------------------------------------------------------------
    def _ensure_constraints(self) -> None:
        """Uniqueness constraints, which also create the backing indexes.

        Without these every MERGE degenerates into a full scan, and traversal
        cost stops being a function of the neighbourhood.
        """
        stmts = [
            "CREATE CONSTRAINT apix_endpoint_id IF NOT EXISTS "
            "FOR (e:Endpoint) REQUIRE e.id IS UNIQUE",
            "CREATE CONSTRAINT apix_service_name IF NOT EXISTS "
            "FOR (s:Service) REQUIRE s.name IS UNIQUE",
        ]
        with self._driver.session(database=self.database) as session:
            for stmt in stmts:
                session.run(stmt)

    # ------------------------------------------------------------------
    def add_endpoint(self, endpoint_id: str, service: str) -> None:
        with self._driver.session(database=self.database) as session:
            session.run(
                """
                MERGE (s:Service {name: $service})
                MERGE (e:Endpoint {id: $endpoint_id})
                MERGE (s)-[:OWNS]->(e)
                """,
                service=service,
                endpoint_id=endpoint_id,
            )

    def add_call(self, caller_service: str, endpoint_id: str) -> None:
        with self._driver.session(database=self.database) as session:
            session.run(
                """
                MATCH (e:Endpoint {id: $endpoint_id})
                OPTIONAL MATCH (owner:Service)-[:OWNS]->(e)
                WITH e, owner
                WHERE owner IS NULL OR owner.name <> $caller
                MERGE (c:Service {name: $caller})
                MERGE (c)-[:CALLS]->(e)
                """,
                endpoint_id=endpoint_id,
                caller=caller_service,
            )

    # ------------------------------------------------------------------
    def blast_radius(self, endpoint_id: str, max_depth: int = 4) -> BlastRadius:
        with self._driver.session(database=self.database) as session:
            direct = [
                r["name"] for r in session.run(
                    """
                    MATCH (s:Service)-[:CALLS]->(e:Endpoint {id: $id})
                    RETURN DISTINCT s.name AS name ORDER BY name
                    """,
                    id=endpoint_id,
                )
            ]
            if not direct:
                return BlastRadius(endpoint_id=endpoint_id)

            # The variable-length traversal. Neo4j does not accept a parameter
            # for the upper bound of a path range, so it is interpolated from an
            # int we control - never from user input.
            depth = max(1, min(int(max_depth), 10)) * 2
            reached = session.run(
                f"""
                MATCH (e:Endpoint {{id: $id}})
                MATCH path = (dep)-[:CALLS|OWNS*1..{depth}]->(e)
                WITH nodes(path) AS ns, length(path) AS hops
                UNWIND ns AS n
                RETURN DISTINCT
                    labels(n)[0] AS kind,
                    coalesce(n.name, n.id) AS key,
                    min(hops) AS hop
                ORDER BY hop, key
                """,
                id=endpoint_id,
            ).data()

        services = [
            r["key"] for r in reached
            if r["kind"] == "Service" and r["key"] not in direct
        ]
        endpoints = [
            (r["key"], int(r["hop"])) for r in reached
            if r["kind"] == "Endpoint" and r["key"] != endpoint_id
        ]
        depth_reached = max((r["hop"] for r in reached), default=1)

        return BlastRadius(
            endpoint_id=endpoint_id,
            direct_services=direct,
            indirect_services=sorted(set(services)),
            affected_endpoints=endpoints,
            depth_reached=int(depth_reached),
            truncated=depth_reached >= depth,
        )

    # ------------------------------------------------------------------
    def stats(self) -> dict[str, int]:
        with self._driver.session(database=self.database) as session:
            rec: dict[str, Any] = session.run(
                """
                OPTIONAL MATCH (e:Endpoint)
                WITH count(DISTINCT e) AS endpoints
                OPTIONAL MATCH (s:Service)
                WITH endpoints, count(DISTINCT s) AS services
                OPTIONAL MATCH ()-[c:CALLS]->()
                RETURN endpoints, services, count(c) AS call_edges
                """
            ).single()
            isolated = session.run(
                """
                MATCH (e:Endpoint)
                WHERE NOT ()-[:CALLS]->(e)
                RETURN count(e) AS n
                """
            ).single()["n"]

        return {
            "endpoints": int(rec["endpoints"]),
            "services": int(rec["services"]),
            "call_edges": int(rec["call_edges"]),
            "isolated_endpoints": int(isolated),
        }

    def close(self) -> None:
        self._driver.close()
