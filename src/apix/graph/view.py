"""
The dependency graph as something to draw: one shape for the demo bank and for
every project scan, so one page renders both.

    services   boxes: a service with the endpoints it serves, a gateway, a
               caller that serves nothing (a batch job, a mobile app), a
               message topic, or a target outside the repository
    endpoints  rows inside a service box
    edges      calls (service -> endpoint), routes (gateway -> service),
               publishes (service -> topic), consumes (topic -> service)
    radius     the blast radius of every endpoint, computed by the same graph
               code the removal gate uses

`basis` says where the edges came from: "traffic" (observed calls, the demo
bank) or "code" (read from a repository, see apix/live/deps.py). The page
states which, because they answer different questions: what does call this,
and what can.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from apix.graph.memory import InMemoryGraph

Endpoint = dict[str, Any]


def _path_of(endpoint_id: str, fallback: str) -> str:
    """The path as the endpoint id spells it.

    The demo estate keeps the version out of `path` (it is a field of its own),
    so `rec.path` reads /accounts/{id} where the endpoint is /v2/accounts/{id}.
    The id is what every other view shows, so the graph uses it too.
    """
    _, _, path = endpoint_id.partition(" ")
    return path or fallback


def _view(basis: str, services: dict[str, dict[str, Any]], endpoints: list[Endpoint],
          edges: list[dict[str, Any]], graph: InMemoryGraph,
          notes: list[str]) -> dict[str, Any]:
    radius = {e["id"]: graph.blast_radius(e["id"]).to_dict() for e in endpoints}
    for e in endpoints:
        r = radius[e["id"]]
        e["callers"] = r["direct_services"]
        e["isolated"] = r["isolated"]
    by_service: dict[str, list[str]] = defaultdict(list)
    for e in endpoints:
        by_service[e["service"]].append(e["id"])
    for name, ids in by_service.items():
        services.setdefault(name, {"id": name, "kind": "service"})
        services[name]["endpoints"] = sorted(ids)
    for s in services.values():
        s.setdefault("endpoints", [])
    return {
        "basis": basis,
        "services": sorted(services.values(), key=lambda s: s["id"]),
        "endpoints": endpoints,
        "edges": edges,
        "radius": radius,
        "notes": notes,
        "stats": {
            "services": sum(1 for s in services.values() if s["kind"] == "service"),
            "endpoints": len(endpoints),
            "calls": sum(1 for e in edges if e["kind"] == "calls"),
            "routes": sum(1 for e in edges if e["kind"] == "routes"),
            "topics": sum(1 for s in services.values() if s["kind"] == "topic"),
            "isolated": sum(1 for r in radius.values() if r["isolated"]),
        },
    }


# ---------------------------------------------------------------------------
def traffic_view(records: list[Any], labels: dict[str, str]) -> dict[str, Any]:
    """The demo bank: edges are callers observed on the wire."""
    graph = InMemoryGraph()
    services: dict[str, dict[str, Any]] = {}
    endpoints: list[Endpoint] = []
    edges: list[dict[str, Any]] = []
    for rec in records:
        graph.add_endpoint(rec.endpoint_id, rec.service)
        endpoints.append({
            "id": rec.endpoint_id, "service": rec.service, "method": rec.method,
            "path": _path_of(rec.endpoint_id, rec.path), "label": labels.get(rec.endpoint_id),
            "daily_calls": rec.daily_calls, "exposed_via": [],
        })
    for rec in records:
        for caller in rec.caller_services:
            graph.add_call(caller, rec.endpoint_id)
            if caller != rec.service:
                services.setdefault(caller, {"id": caller, "kind": "service"})
                edges.append({
                    "kind": "calls", "from": caller, "to": rec.endpoint_id,
                    "evidence": "observed on the wire during the capture window",
                })
    return _view("traffic", services, endpoints, edges, graph, [
        "Edges are calls observed in traffic during the capture window. A caller "
        "silent in that window, like a month-end batch job, does not appear: that is "
        "what Safe Kill's shadow window exists to catch.",
    ])


def code_view(records: list[Any], deps: Any, findings: dict[str, int]) -> dict[str, Any]:
    """A project scan: edges read from the code (apix.live.deps)."""
    from apix.live.deps import match_endpoint, route_matches

    graph = InMemoryGraph()
    services: dict[str, dict[str, Any]] = {}
    endpoints: list[Endpoint] = []
    edges: list[dict[str, Any]] = []
    notes: list[str] = []

    for rec in records:
        graph.add_endpoint(rec.endpoint_id, rec.service)
        endpoints.append({
            "id": rec.endpoint_id, "service": rec.service, "method": rec.method,
            "path": _path_of(rec.endpoint_id, rec.path), "label": None,
            "findings": findings.get(rec.endpoint_id, 0),
            "exposed_via": [],
        })
    table = [(e["id"], e["method"], e["path"], e["service"]) for e in endpoints]

    unmatched = 0
    for call in deps.calls:
        services.setdefault(call.caller_service, {"id": call.caller_service, "kind": "service"})
        evidence = f"{call.client} call in {call.file}:{call.line}"
        target = match_endpoint(call, table)
        if target:
            graph.add_call(call.caller_service, target)
            edges.append({"kind": "calls", "from": call.caller_service, "to": target,
                          "evidence": evidence, "file": call.file, "line": call.line})
            continue
        unmatched += 1
        ext = f"outside: {call.target_host}" if call.target_host else "outside this repository"
        services.setdefault(ext, {"id": ext, "kind": "external", "endpoints": []})
        edges.append({"kind": "calls", "from": call.caller_service, "to": ext,
                      "label": f"{call.method} {call.path}",
                      "evidence": evidence + " (no endpoint in this repository matches)",
                      "file": call.file, "line": call.line})

    for route in deps.routes:
        services.setdefault(route.gateway_service,
                            {"id": route.gateway_service, "kind": "gateway"})
        services[route.gateway_service]["kind"] = "gateway"
        hit = [e for e in endpoints if route_matches(route.pattern, e["path"])]
        for e in hit:
            e["exposed_via"].append(f"{route.gateway_service} {route.pattern}")
        targets = sorted({e["service"] for e in hit})
        for target in targets or [f"outside: {route.target}"]:
            if target.startswith("outside: "):
                services.setdefault(target, {"id": target, "kind": "external", "endpoints": []})
            edges.append({
                "kind": "routes", "from": route.gateway_service, "to": target,
                "label": route.pattern,
                "count": sum(1 for e in hit if e["service"] == target),
                "evidence": f"route {route.pattern} in {route.file}:{route.line}",
                "file": route.file, "line": route.line,
            })

    for use in deps.topics:
        topic = f"topic: {use.topic}"
        services.setdefault(topic, {"id": topic, "kind": "topic", "broker": use.broker,
                                    "endpoints": []})
        services.setdefault(use.service, {"id": use.service, "kind": "service"})
        how = "read" if use.certain else "inferred from a topic the service declares"
        edge = {
            "kind": use.role, "certain": use.certain,
            "evidence": f"{use.broker} {use.role[:-1]} in {use.file}:{use.line} ({how})",
            "file": use.file, "line": use.line,
        }
        if use.role == "publishes":
            edge.update({"from": use.service, "to": topic})
        else:
            edge.update({"from": topic, "to": use.service})
        edges.append(edge)

    internal = [e for e in endpoints if e["exposed_via"]
                and any(w in e["path"].lower() for w in ("internal", "admin", "debug"))]
    if internal:
        notes.append(
            f"{len(internal)} endpoint(s) with internal, admin or debug in the path are "
            "also matched by a public gateway route, e.g. "
            f"{internal[0]['id']} via {internal[0]['exposed_via'][0]}. Check that "
            "something other than the route keeps them private."
        )
    if unmatched:
        notes.append(f"{unmatched} call(s) reach nothing in this repository: another "
                     "repository's service, or a third-party API.")
    notes.append(
        f"Read from {deps.files_read} source and config files; {deps.test_files_skipped} "
        "test file(s) were left out, because a call in a test is not a dependency in "
        "production. Callers outside the repository cannot appear."
    )
    return _view("code", services, endpoints, edges, graph, notes)
