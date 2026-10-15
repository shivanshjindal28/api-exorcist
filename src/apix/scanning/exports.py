"""
A scan's results in the formats other systems already read.

    sarif     SARIF 2.1.0. GitHub code scanning, Azure DevOps and most security
              dashboards import it, so findings land where developers look
    csv       the inventory, one row per endpoint, for a spreadsheet or a GRC tool
    openapi   an OpenAPI 3.1 skeleton for every undocumented endpoint: the
              "needs documentation" decision, started for the team

Every export says where it came from and what it is not: candidates are
suspected, and lifecycle labels exist only where access logs were imported.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any

from apix import __version__

TOOL_URI = "https://github.com/shivanshjindal28/api-exorcist"

_RULES = {
    "zombie": ("ZombieEndpoint", "Endpoint with no successful use in the logged window",
               "error"),
    "candidate": ("ZombieCandidate", "Endpoint the code evidence suggests is no longer used",
                  "warning"),
    "shadow": ("ShadowEndpoint", "Endpoint served by the code but absent from the API "
               "specification", "warning"),
    "deprecated": ("DeprecatedStillServed", "Endpoint marked deprecated that is still served",
                   "warning"),
    "orphaned": ("OrphanedEndpoint", "Endpoint in use with no owning team recorded", "note"),
}


def _usage(traffic: dict[str, Any] | None, eid: str) -> dict[str, Any]:
    return ((traffic or {}).get("endpoints") or {}).get(eid) or {}


def sarif(job: dict[str, Any], traffic: dict[str, Any] | None) -> dict[str, Any]:
    report = job["report"]
    results: list[dict[str, Any]] = []
    for e in report["endpoints"]:
        use = _usage(traffic, e["id"])
        hits: list[tuple[str, str]] = []
        if use.get("lifecycle") == "ZOMBIE":
            hits.append(("zombie", use["reason"]))
        elif e.get("candidate"):
            c = e["candidate"]
            hits.append(("candidate", f"{c['label']} (score {c['score']}): "
                         + "; ".join(s["text"] for s in c["signals"] if s["weight"] > 0)))
        if not e.get("documented"):
            hits.append(("shadow", "not in the API specification"))
        if e.get("deprecated_in_spec") and use.get("lifecycle") != "ZOMBIE":
            hits.append(("deprecated", "marked deprecated in the specification and still "
                         "served"))
        if use.get("lifecycle") == "ORPHANED":
            hits.append(("orphaned", use["reason"]))
        for key, text in hits:
            rule_id, _, level = _RULES[key]
            r: dict[str, Any] = {
                "ruleId": rule_id,
                "level": level,
                "message": {"text": f"{e['id']}: {text}"},
                "properties": {
                    "endpoint": e["id"],
                    "sensitivity": (e.get("sensitivity") or {}).get("category"),
                    "priority": e.get("priority"),
                },
            }
            if e.get("file"):
                r["locations"] = [{"physicalLocation": {
                    "artifactLocation": {"uri": e["file"]},
                    "region": {"startLine": int(e.get("line") or 1)},
                }}]
            results.append(r)
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {
                "name": "API Exorcist", "version": __version__,
                "informationUri": TOOL_URI,
                "rules": [{"id": rid, "shortDescription": {"text": desc},
                           "defaultConfiguration": {"level": level}}
                          for rid, desc, level in _RULES.values()],
            }},
            "versionControlProvenance": ([{
                "repositoryUri": "https://" + job["target"],
                "revisionId": report["details"]["commit"],
            }] if job.get("kind") == "github" and report.get("details", {}).get("commit")
                else []),
            "results": results,
        }],
    }


CSV_COLUMNS = ["endpoint", "method", "path", "service", "file", "line", "framework",
               "documented", "owner", "last_change_days", "sensitivity", "priority",
               "candidate", "candidate_score", "lifecycle", "requests", "last_success",
               "review"]


def inventory_csv(job: dict[str, Any], traffic: dict[str, Any] | None,
                  reviews: dict[str, dict[str, Any]]) -> str:
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(CSV_COLUMNS)
    for e in sorted(job["report"]["endpoints"], key=lambda x: -int(x.get("priority") or 0)):
        use = _usage(traffic, e["id"])
        cand = e.get("candidate") or {}
        w.writerow([_safe(v) for v in [
            e["id"], e["method"], e["path"], e.get("service") or "", e.get("file") or "",
            e.get("line") or "", e.get("framework") or "", "yes" if e.get("documented") else "no",
            e.get("owner") or "", "" if e.get("last_change_days") is None else e["last_change_days"],
            (e.get("sensitivity") or {}).get("category", ""), e.get("priority", ""),
            cand.get("label", ""), cand.get("score", ""), use.get("lifecycle", ""),
            use.get("requests", ""), use.get("last_success") or "",
            (reviews.get(e["id"]) or {}).get("label", ""),
        ]])
    return out.getvalue()


def _safe(value: Any) -> Any:
    """Defuse spreadsheet formulas: a path or note beginning with = + - @ is data."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def openapi_stubs(job: dict[str, Any]) -> dict[str, Any]:
    paths: dict[str, dict[str, Any]] = {}
    for e in job["report"]["endpoints"]:
        if e.get("documented"):
            continue
        params = re.findall(r"\{([^}]+)\}", e["path"])
        op: dict[str, Any] = {
            "summary": f"TODO: describe {e.get('function') or e['id']}",
            "operationId": e.get("function") or None,
            "tags": [e.get("service") or "default"],
            "x-owner": e.get("owner") or "TODO",
            "x-source": f"{e['file']}:{e.get('line') or 1}" if e.get("file") else None,
            "responses": {"default": {"description": "TODO"}},
        }
        if params:
            op["parameters"] = [{"name": p, "in": "path", "required": True,
                                 "schema": {"type": "string"}} for p in params]
        if e.get("candidate"):
            op["x-apix-candidate"] = e["candidate"]["label"]
        paths.setdefault(e["path"], {})[e["method"].lower()] = {
            k: v for k, v in op.items() if v is not None}
    return {
        "openapi": "3.1.0",
        "info": {
            "title": f"Undocumented endpoints of {job['target']}",
            "version": "0.0.0-draft",
            "description": "Generated by API Exorcist from the code. Every operation here "
                           "is served but was absent from the specification. Fill in the "
                           "TODOs, or retire the endpoint instead of documenting it.",
        },
        "paths": dict(sorted(paths.items())),
    }
