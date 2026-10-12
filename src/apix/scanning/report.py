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

from apix.connectors.base import Source
from apix.live.scan import RepoScanResult

OK, PARTIAL, UNAVAILABLE, FAILED = "ok", "partial", "unavailable", "failed"

STALE_DAYS = 365


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
        counts.update(v.findings)
    universal = sorted(s for s, n in counts.items() if total and n == total)

    by_id = {r.endpoint_id: r for r in result.records}
    endpoints: list[dict[str, Any]] = []
    for v in sorted(result.verdicts, key=lambda x: (-x.risk_score, x.endpoint_id)):
        rec = by_id.get(v.endpoint_id)
        code = (rec.evidence.get(Source.CODE.value) or {}) if rec else {}
        seen = sorted(rec.seen_by) if rec else []
        endpoints.append({
            "id": v.endpoint_id,
            "method": rec.method if rec else v.endpoint_id.split(" ", 1)[0],
            "path": rec.path if rec else v.endpoint_id.split(" ", 1)[-1],
            "file": code.get("source_file"),
            "line": code.get("source_line"),
            "framework": code.get("framework"),
            "owner": rec.owner_team if rec else None,
            "last_change_days": rec.days_since_last_commit if rec else None,
            "documented": Source.OPENAPI.value in seen,
            "deprecated_in_spec": bool(rec and rec.spec_deprecated),
            "seen_by": seen,
            "flags": list(rec.flags) if rec else [],
            "findings": [f for f in v.findings if f not in universal],
            "risk": v.risk_score,
        })

    undocumented = sum(1 for e in endpoints if not e["documented"])
    unowned = sum(1 for e in endpoints if not e["owner"])
    stale = sum(1 for e in endpoints
                if e["last_change_days"] is not None and e["last_change_days"] > STALE_DAYS)
    summary = [
        {"label": "Endpoints found", "value": total},
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
        "lifecycle": {
            "available": False,
            "why": "No usage data: a project's files cannot show whether an endpoint "
                   "is still called.",
        },
        "details": {
            "commit": result.head_commit or None,
            "specifications": result.spec_files,
            "mount_prefixes": result.mount_prefixes,
        },
    }
