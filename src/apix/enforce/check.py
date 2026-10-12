"""
Compare the merge base with the pull request's head, and judge only the change.

Pre-existing debt never fails a check. An estate with four hundred undocumented
endpoints can adopt enforcement today: from then on it cannot gain a four
hundred and first. A gate that failed every pull request on day one for the
sins of the past would be switched off by day two.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from apix.enforce.config import (
    HANDLER_KEPT,
    SPEC_WITHOUT_HANDLER,
    UNDOCUMENTED,
    UNOWNED,
    AllowRule,
    EnforceConfig,
)
from apix.enforce.snapshot import Snapshot


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str           # "error" | "warn"
    endpoint_id: str
    message: str
    file: str | None = None
    line: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "endpoint_id": self.endpoint_id,
            "message": self.message,
            "file": self.file,
            "line": self.line,
        }


@dataclass
class Comparison:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    exempted: list[tuple[str, AllowRule]] = field(default_factory=list)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "warn"]

    @property
    def passed(self) -> bool:
        return not self.errors


def compare(base: Snapshot, head: Snapshot, config: EnforceConfig) -> Comparison:
    result = Comparison(
        added=sorted(set(head.routes) - set(base.routes)),
        removed=sorted(set(base.routes) - set(head.routes)),
    )

    def add(rule: str, endpoint_id: str, message: str,
            file: str | None = None, line: int | None = None) -> None:
        severity = config.severity[rule]
        if severity == "off":
            return
        result.findings.append(Finding(rule, severity, endpoint_id, message, file, line))

    # -- endpoints this change adds ----------------------------------------
    for eid in result.added:
        exemption = config.allowed_by(eid)
        if exemption:
            result.exempted.append((eid, exemption))
            continue
        route = head.routes[eid]
        entry, certain = head.documentation_of(route)
        if entry is None:
            note = "" if route.prefix_resolved else (
                " Its mount prefix could not be resolved, so only a suffix match "
                "was possible, and none was found."
            )
            add(UNDOCUMENTED, eid,
                f"{eid} is added with no OpenAPI entry: an undocumented endpoint is "
                f"a shadow API from its first commit.{note}",
                route.file, route.line)
        elif not certain and config.severity[UNDOCUMENTED] != "off":
            # Documented by a suffix match only: say so, never pretend. Always a
            # warning, since the match is probable rather than established.
            result.findings.append(Finding(
                UNDOCUMENTED, "warn", eid,
                f"{eid} matches documented {entry.file} only by path suffix, "
                "because its mount prefix could not be resolved.",
                route.file, route.line,
            ))
        if head.owner_of(eid) is None:
            add(UNOWNED, eid,
                f"{eid} is added with no owner: no CODEOWNERS entry covers "
                f"{route.file} and its spec entry has no x-owner. An endpoint "
                "nobody owns is how an orphan starts.",
                route.file, route.line)

    # -- documentation this change removes while the code stays -------------
    for eid in sorted(set(base.spec) - set(head.spec)):
        kept = head.routes.get(eid)
        if kept is None or config.allowed_by(eid):
            continue
        add(HANDLER_KEPT, eid,
            f"{eid} is removed from the specification but its handler remains in "
            f"{kept.file}. This is how a zombie is born: the endpoint keeps "
            "serving after everyone has been told it is gone. Delete the handler "
            "too, or keep it documented.",
            kept.file, kept.line)

    # -- documentation this change adds with nothing behind it --------------
    for eid in sorted(set(head.spec) - set(base.spec)):
        if eid in head.routes or config.allowed_by(eid):
            continue
        method, _, path = eid.partition(" ")
        if any(r.method == method and not r.prefix_resolved and path.endswith(r.path)
               for r in head.routes.values()):
            continue
        add(SPEC_WITHOUT_HANDLER, eid,
            f"{eid} is newly documented in {head.spec[eid].file} but no handler "
            "for it was found in the code. Either it is not built yet, or route "
            "extraction does not cover its framework.",
            head.spec[eid].file)

    return result
