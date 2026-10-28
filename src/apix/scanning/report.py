"""
The report a scan produces, in the one shape the browser renders.

A report has four parts:

    summary     the headline counts
    checks      every stage, and whether it worked: ok, partial, unavailable
                or failed, each with a reason a person can act on
    endpoints   what was found, with the findings behind each
    repository  findings true of every endpoint, which therefore rank none

`checks` is the important one. A scan that silently skips a stage looks the
same as a scan that found nothing, and the second is a claim the first cannot
make. Every stage that could not run says why, here, in plain words.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from apix import __version__
from apix.connectors.base import Source
from apix.live.scan import RepoScanResult

OK, PARTIAL, UNAVAILABLE, FAILED = "ok", "partial", "unavailable", "failed"


def _problem_keys() -> frozenset[str]:
    """Rules whose firing points at a problem, not at health.

    A verdict's supporting reasons include positive evidence ("an owning team
    is recorded"), and the first version of this report listed those as
    findings, so a healthy endpoint showed a finding that read like praise.
    """
    from apix.engine.rules import RULES
    from apix.engine.verdict import Classification

    keys = {r.key for r in RULES if r.weights.get(Classification.ZOMBIE, 0) > 0}
    return frozenset(keys | {"MARKED_DEPRECATED", "UNOWNED_BUT_USED"})


PROBLEMS = _problem_keys()


def findings_of(v: Any) -> list[str]:
    return [r.statement for r in v.reasons if r.key in PROBLEMS and r.contribution > 0]

STALE_DAYS = 365


def _service_for(rec: Any, code: dict[str, Any]) -> str:
    """The service an endpoint belongs to. One found only in a specification
    used to be named after the spec's folder ("openapi-spec" in crAPI); its
    path names the service better (/workshop/api/... -> workshop)."""
    if rec is None:
        return ""
    if code.get("source_file"):
        return str(rec.service)
    name = str(rec.service).lower()
    if name in ("root", "src", "docs", "doc", "api") or any(
            w in name for w in ("spec", "openapi", "swagger", "api-docs")):
        first = next((s for s in str(rec.path).split("/") if s and not s.startswith("{")), "")
        return first or str(rec.service)
    return str(rec.service)


def check(name: str, status: str, detail: str) -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail}


def repository_report(
    result: RepoScanResult,
    *,
    has_history: bool,
    acquired: dict[str, str],
) -> dict[str, Any]:
    """Build the report for a GitHub or uploaded-folder scan."""
    checks: list[dict[str, str]] = [acquired]

    # -- route extraction ------------------------------------------------------
    if result.extractor_error and not result.routes_found:
        reason = result.extractor_error
        if "not installed" in reason:
            reason = ("Semgrep is not installed on the machine running API Exorcist, "
                      "so routes cannot be read from code. Install it with "
                      "`pip install semgrep` and scan again")
        checks.append(check("API routes in the code", FAILED, reason))
    elif result.routes_found == 0:
        checks.append(check(
            "API routes in the code", UNAVAILABLE,
            "no HTTP routes were found. The project may not serve an API, or may use a "
            "framework the extractor does not cover yet (supported: FastAPI, Flask, "
            "Express, Spring)",
        ))
    else:
        frameworks = sorted({
            str((r.evidence.get(Source.CODE.value) or {}).get("framework") or "")
            for r in result.records
        } - {""})
        checks.append(check(
            "API routes in the code", OK,
            f"{result.routes_found} route declaration(s) found by AST analysis"
            + (f" ({', '.join(frameworks)})" if frameworks else ""),
        ))
    if result.spec_wired_routes:
        checks.append(check(
            "Handlers wired by the specification", OK,
            f"{result.spec_wired_routes} endpoint(s) are routed by their OpenAPI "
            "operationId (Connexion or API-first code generation), not a route "
            "declaration; each handler was found by that name",
        ))
    for expr, value in (result.resolved_mounts or {}).items():
        checks.append(check(
            "Full route paths", OK,
            f"routes are mounted under {expr}, which the project sets to {value!r}; "
            "that value is applied",
        ))
    if result.unresolved_prefix_routes:
        named = (f"by {', '.join(result.variable_mounts)}" if result.variable_mounts
                 else "in more than one place")
        checks.append(check(
            "Full route paths", PARTIAL,
            f"{result.unresolved_prefix_routes} route(s) are mounted under a prefix set "
            f"{named}. Their paths are shown without that prefix, because knowing its "
            "value would mean running the project's configuration, and nothing from a "
            "scanned project is ever run",
        ))

    # -- specification -------------------------------------------------------
    if result.spec_files:
        checks.append(check("API specification", OK,
                            "parsed: " + ", ".join(result.spec_files)))
    else:
        checks.append(check(
            "API specification", UNAVAILABLE,
            "no OpenAPI or Swagger file in the project. Every endpoint therefore counts "
            "as undocumented. If the project generates its specification at run time "
            "(FastAPI does), that version is not in the files to read",
        ))

    # -- history -------------------------------------------------------------
    if not has_history:
        checks.append(check(
            "Change history", UNAVAILABLE,
            "an uploaded folder does not include git history, so when each handler last "
            "changed is unknown and nothing is flagged as stale. Scan the GitHub link "
            "instead to include it",
        ))
    elif result.total_commits < 20:
        checks.append(check(
            "Change history", PARTIAL,
            f"only {result.total_commits} commit(s); staleness means little this early",
        ))
    else:
        checks.append(check("Change history", OK,
                            f"{result.total_commits} commits read for per-file staleness"))

    # -- ownership and pipelines ---------------------------------------------
    checks.append(
        check("Ownership (CODEOWNERS)", OK, f"{result.codeowners_rules} rule(s)")
        if result.codeowners_rules else
        check("Ownership (CODEOWNERS)", UNAVAILABLE,
              "no CODEOWNERS file, so no endpoint has a known owning team")
    )
    checks.append(
        check("CI/CD pipelines", OK, f"{result.workflow_count} workflow file(s)")
        if result.workflow_count else
        check("CI/CD pipelines", UNAVAILABLE,
              "no GitHub Actions workflows found, so no deployment evidence")
    )

    # -- dependencies between services, and the project's own clients ---------
    from apix.live.clients import ClientRef, match_refs

    graph = None
    deps = result.dependencies
    clients = result.client_refs
    table = [(r.endpoint_id, r.method, r.endpoint_id.split(" ", 1)[-1], r.service)
             for r in result.records]
    client_matches = match_refs(clients.refs, table) if clients is not None else []
    if deps is not None:
        from apix.graph.view import code_view

        own = {v.endpoint_id: len(findings_of(v)) for v in result.verdicts}
        graph = code_view(result.records, deps, own, client_matches)
        st = graph["stats"]
        n_topics = len({t.topic for t in deps.topics})
        if st["calls"] or st["routes"] or n_topics:
            checks.append(check(
                "Dependencies between services", OK,
                f"{st['calls']} call(s) between services, {st['routes']} gateway "
                f"route(s) and {n_topics} message topic(s) read from code. This shows "
                "what the code can call; callers outside the repository cannot appear",
            ))
        else:
            checks.append(check(
                "Dependencies between services", UNAVAILABLE,
                "no calls between services, gateway routes or message topics were found "
                "in the code, so every endpoint appears isolated. Either the project is "
                "a single service, or its clients build their URLs at run time",
            ))

    referenced: dict[str, list[str]] = {}
    for ref, eid in client_matches:
        referenced.setdefault(eid, []).append(f"{ref.file}:{ref.line}, {ref.via}")
    uncalled: dict[str, str] = {}
    if clients is not None:
        fake = [ClientRef("__generated__", path, method, "", 0, name)
                for name, method, path in clients.uncalled_generated]
        for ref, eid in match_refs(fake, table):
            uncalled.setdefault(eid, ref.via)
        n_refs = len(referenced)
        if n_refs or clients.uncalled_generated:
            detail = (f"{n_refs} endpoint(s) are referenced by the project's own client "
                      f"code ({clients.client_files} file(s) read)")
            if clients.generated_files:
                detail += (f"; a generated client is present, and {len(uncalled)} of its "
                           "functions are never called")
            checks.append(check("This project's own clients", OK, detail))
        else:
            checks.append(check(
                "This project's own clients", UNAVAILABLE,
                "no client code in the repository (front end, SDK or other service) "
                "references these endpoints, so whether its clients use them cannot be "
                "judged from here",
            ))

    # -- what a repository can never show ------------------------------------
    checks.append(check(
        "Traffic, gateway and DNS", UNAVAILABLE,
        "a project's files cannot show whether anyone still calls an endpoint. Active, "
        "deprecated, orphaned and zombie are all defined by usage, so this scan "
        "reports findings and does not label any endpoint a zombie",
    ))

    # -- endpoints -----------------------------------------------------------
    total = len(result.verdicts)
    counts: Counter[str] = Counter()
    for v in result.verdicts:
        counts.update(findings_of(v))
    universal = sorted(s for s, n in counts.items() if total and n == total)

    by_id = {r.endpoint_id: r for r in result.records}
    endpoints: list[dict[str, Any]] = []
    for v in sorted(result.verdicts, key=lambda x: (-x.risk_score, x.endpoint_id)):
        rec = by_id.get(v.endpoint_id)
        code = (rec.evidence.get(Source.CODE.value) or {}) if rec else {}
        seen = sorted(rec.seen_by) if rec else []
        endpoints.append({
            "id": v.endpoint_id,
            "service": _service_for(rec, code),
            "function": code.get("handler_function"),
            "method": rec.method if rec else v.endpoint_id.split(" ", 1)[0],
            "path": rec.path if rec else v.endpoint_id.split(" ", 1)[-1],
            "file": code.get("source_file"),
            "line": code.get("source_line"),
            "framework": code.get("framework"),
            "declared_path": code.get("declared_path"),
            "prefix_resolved": code.get("prefix_resolved"),
            "owner": rec.owner_team if rec else None,
            "last_change_days": rec.days_since_last_commit if rec else None,
            "documented": Source.OPENAPI.value in seen,
            "deprecated_in_spec": bool(rec and rec.spec_deprecated),
            "seen_by": seen,
            "flags": list(rec.flags) if rec else [],
            "findings": [f for f in findings_of(v) if f not in universal],
            "risk": v.risk_score,
        })

    # -- zombie candidates: what the code evidence adds up to -----------------
    from apix.live.evidence import rank

    called_by_services: dict[str, list[str]] = {}
    exposed: dict[str, list[str]] = {}
    if graph is not None:
        for edge in graph["edges"]:
            if edge["kind"] == "calls" and not edge.get("client"):
                called_by_services.setdefault(edge["to"], []).append(edge["from"])
        exposed = {e["id"]: e["exposed_via"] for e in graph["endpoints"] if e["exposed_via"]}
    # Endpoints a front end or app uses: referenced from front-end code, or
    # called through a generated client.
    frontend = {eid for ref, eid in client_matches
                if ref.frontend or "generated client" in ref.via}
    candidates = rank(
        endpoints, referenced=referenced, frontend_referenced=frontend,
        called_by_services=called_by_services,
        uncalled_generated=uncalled, exposed_via=exposed,
        markers=result.code_markers or {}, newest_change_days=result.newest_change_days,
    )
    by_candidate = {c.endpoint_id: c.to_dict() for c in candidates}
    for e in endpoints:
        e["candidate"] = by_candidate.get(e["id"])
        e["referenced_by"] = referenced.get(e["id"], [])[:3]
    likely = sum(1 for c in candidates if c.label == "Likely zombie")

    undocumented = sum(1 for e in endpoints if not e["documented"])
    unowned = sum(1 for e in endpoints if not e["owner"])
    stale = sum(1 for e in endpoints
                if e["last_change_days"] is not None and e["last_change_days"] > STALE_DAYS)
    summary = [
        {"label": "Endpoints found", "value": total},
        {"label": "Zombie candidates", "value": len(candidates)},
        {"label": "Likely zombies", "value": likely},
        {"label": "Undocumented", "value": undocumented},
        {"label": "No owner", "value": unowned},
        {"label": "Unchanged for over a year",
         "value": stale if has_history else "unknown"},
        {"label": "Deprecated in spec",
         "value": sum(1 for e in endpoints if e["deprecated_in_spec"])},
    ]
    return {
        "summary": summary,
        "checks": checks,
        "endpoints": endpoints,
        "repository_findings": universal,
        "candidates": [c.to_dict() for c in candidates],
        "graph": graph,
        "sources": {
            "consulted": sorted(s.value for s in result.consulted),
            "unavailable": sorted(s.value for s in result.unavailable),
        },
        "lifecycle": {
            "available": False,
            "why": "Candidates are suspected from code evidence: versions, deprecation "
                   "markers, what the project's own clients call, and history. Proving an "
                   "endpoint dead takes usage data, which a project's files do not hold.",
        },
        "details": {
            "scanner_version": __version__,
            "commit": result.head_commit or None,
            "specifications": result.spec_files,
            "mount_prefixes": result.mount_prefixes,
        },
    }
